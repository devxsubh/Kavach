import pytest

from kavach.exceptions import SignatureError
from kavach.models import OfferPayload
from kavach.protocol import EnvelopeCodec, Identity, MessageBus
from kavach.signing import KeyPair, digest


def test_signed_envelope_and_transcript_chain():
    identities = {name: Identity(name, KeyPair()) for name in ("buyer", "seller")}
    codec = EnvelopeCodec(identities)
    bus = MessageBus(codec)
    first = bus.make_envelope(conversation_id="c", sender_id="buyer", recipient_id="seller", msg_type="OFFER", payload=OfferPayload(product_id="p", price_minor=10))
    import asyncio
    asyncio.run(bus.send(first))
    second = bus.make_envelope(conversation_id="c", sender_id="seller", recipient_id="buyer", msg_type="COUNTER", payload=OfferPayload(product_id="p", price_minor=12))
    asyncio.run(bus.send(second))
    assert bus.replay_hash("c") != "GENESIS"
    assert bus.transcripts["c"].messages[1].prev_hash == digest(bus.transcripts["c"].messages[0].model_dump(mode="json"))


def test_tampered_envelope_is_rejected():
    identities = {name: Identity(name, KeyPair()) for name in ("buyer", "seller")}
    codec = EnvelopeCodec(identities)
    bus = MessageBus(codec)
    envelope = bus.make_envelope(conversation_id="c", sender_id="buyer", recipient_id="seller", msg_type="OFFER", payload=OfferPayload(product_id="p", price_minor=10))
    tampered = envelope.model_copy(update={"payload": OfferPayload(product_id="p", price_minor=999)})
    with pytest.raises(SignatureError):
        import asyncio
        asyncio.run(bus.send(tampered))
