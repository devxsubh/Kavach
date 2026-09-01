from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models import Product
from ..world import Database
from .core import GuardrailKernel


class SearchCatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1)
    category: str | None = None
    max_results: int = Field(default=10, ge=1, le=10)


class ProductDetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)


def search_catalog(db: Database, kernel: GuardrailKernel, request: SearchCatalogInput) -> list[Product]:
    products = db.search_products(request.category)[: request.max_results]
    return kernel.register_candidates(request.session_id, products)


def get_product_detail(db: Database, kernel: GuardrailKernel, request: ProductDetailInput) -> Product:
    product = db.get_product(request.product_id)
    kernel.sanitize_untrusted(request.session_id, "product_title", product.title)
    kernel.sanitize_untrusted(request.session_id, "product_description", product.description)
    return product.model_copy(deep=True)
