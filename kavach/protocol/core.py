from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..exceptions import SignatureError
from ..models import Envelope
from ..signing import KeyPair, canonical_bytes, digest


class Transcript:
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.messages: list[Envelope] = []

    @property
    def head_hash(self) -> str:
        return digest(self.messages[-1].model_dump(mode="json")) if self.messages else "GENESIS"

    def append(self, envelope: Envelope) -> Envelope:
        expected_seq = len(self.messages)
        expected_prev = self.head_hash
        if envelope.seq != expected_seq or envelope.prev_hash != expected_prev:
            raise SignatureError("transcript sequence or previous hash mismatch")
        self.messages.append(envelope)
        return envelope


@dataclass
class Identity:
    agent_id: str
    keypair: KeyPair


class EnvelopeCodec:
    def __init__(self, identities: dict[str, Identity]):
        self.identities = identities

    def sign(self, envelope: Envelope) -> Envelope:
        identity = self.identities[envelope.sender_id]
        unsigned = envelope.model_copy(update={"signature": ""})
        return envelope.model_copy(update={"signature": identity.keypair.sign(unsigned.model_dump(mode="json"))})

    def verify(self, envelope: Envelope) -> None:
        identity = self.identities.get(envelope.sender_id)
        if identity is None:
            raise SignatureError(f"unknown sender {envelope.sender_id}")
        unsigned = envelope.model_copy(update={"signature": ""})
        KeyPair.verify(identity.keypair.public_b64, unsigned.model_dump(mode="json"), envelope.signature)


Handler = Callable[[Envelope], Awaitable[None]]


class MessageBus:
    def __init__(self, codec: EnvelopeCodec, max_messages: int = 50):
        self.codec = codec
        self.max_messages = max_messages
        self.transcripts: dict[str, Transcript] = {}
        self.handlers: dict[str, Handler] = {}
        self.message_count: defaultdict[str, int] = defaultdict(int)

    def register(self, agent_id: str, handler: Handler) -> None:
        self.handlers[agent_id] = handler

    async def send(self, envelope: Envelope) -> Envelope:
        self.codec.verify(envelope)
        transcript = self.transcripts.setdefault(envelope.conversation_id, Transcript(envelope.conversation_id))
        if self.message_count[envelope.conversation_id] >= self.max_messages:
            raise RuntimeError("GR-11: conversation message limit exceeded")
        stored = transcript.append(envelope)
        self.message_count[envelope.conversation_id] += 1
        if handler := self.handlers.get(envelope.recipient_id):
            await handler(stored)
        return stored

    def make_envelope(self, *, conversation_id: str, sender_id: str, recipient_id: str, msg_type: str, payload: object) -> Envelope:
        transcript = self.transcripts.setdefault(conversation_id, Transcript(conversation_id))
        return self.codec.sign(Envelope(conversation_id=conversation_id, seq=len(transcript.messages), sender_id=sender_id, recipient_id=recipient_id, type=msg_type, payload=payload, prev_hash=transcript.head_hash))

    def replay_hash(self, conversation_id: str) -> str:
        return self.transcripts[conversation_id].head_hash
