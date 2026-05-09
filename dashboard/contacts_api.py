"""
ForgeMarketing Public REST API — Contacts & Leads
=================================================

OpenAPI 3.x blueprint served at /api/v1/
Swagger UI  →  /api/v1/docs
ReDoc       →  /api/v1/redoc
OpenAPI JSON→  /api/v1/openapi.json

Authentication
--------------
All endpoints require an ``X-API-Key`` header containing a key issued via
the admin panel (Admin → API Keys).  Keys are bcrypt-hashed in the database;
only the first 8 characters are stored in plaintext for fast lookup.
"""

from __future__ import annotations

import secrets
import string
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import bcrypt
from flask import request, jsonify, g
from flask_smorest import Blueprint
from flask.views import MethodView
from marshmallow import Schema, fields, validate, validates, ValidationError

from dashboard.models import db, Contact, ExternalAPIKey

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blueprint – registered via flask_smorest.Api in app.py
# ---------------------------------------------------------------------------

contacts_v1 = Blueprint(
    "contacts_v1",
    __name__,
    url_prefix="/api/v1",
    description=(
        "ForgeMarketing CRM API — create and manage contacts/leads.  "
        "Authenticate with **X-API-Key** header.  "
        "Keys are issued from the Admin → API Keys panel."
    ),
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_ALPHABET = string.ascii_letters + string.digits


def _generate_raw_key(length: int = 40) -> str:
    """Return a cryptographically-random API key string."""
    return "fmk_" + "".join(secrets.choice(_ALPHABET) for _ in range(length))


def create_api_key(name: str, scopes: list[str] | None = None,
                   allowed_brands: list[str] | None = None,
                   created_by: str = "system") -> tuple[ExternalAPIKey, str]:
    """
    Create a new ExternalAPIKey row.
    Returns (model_instance, raw_key_plaintext).
    Caller must db.session.add/commit and show raw_key to the user — it is
    NOT stored and cannot be recovered.
    """
    raw = _generate_raw_key()
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    key = ExternalAPIKey(
        name=name,
        key_prefix=raw[:8],
        key_hash=hashed,
        allowed_brands=str(allowed_brands or []).replace("'", '"'),
        scopes=str(scopes or ["contacts:write", "contacts:read"]).replace("'", '"'),
        created_by=created_by,
    )
    import json
    key.allowed_brands = json.dumps(allowed_brands or [])
    key.scopes = json.dumps(scopes or ["contacts:write", "contacts:read"])
    return key, raw


def _authenticate_request(required_scope: str) -> ExternalAPIKey | None:
    """
    Validate the X-API-Key header.
    Returns the ExternalAPIKey row on success, raises a 401/403 Flask response
    (as an exception) on failure.
    """
    raw_key = request.headers.get("X-API-Key", "").strip()
    if not raw_key:
        return None

    prefix = raw_key[:8]
    candidates = ExternalAPIKey.query.filter_by(
        key_prefix=prefix, is_active=True
    ).all()

    matched: ExternalAPIKey | None = None
    for candidate in candidates:
        if candidate.check_key(raw_key):
            matched = candidate
            break

    if matched is None:
        return None

    if required_scope and required_scope not in matched.get_scopes():
        return None

    # Stamp last_used
    try:
        matched.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return matched


def require_scope(scope: str):
    """Decorator: enforce API key auth + scope for MethodView methods."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = _authenticate_request(scope)
            if key is None:
                return jsonify({
                    "error": "Unauthorized",
                    "detail": "Valid X-API-Key header with required scope is missing.",
                }), 401
            g.api_key = key
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Marshmallow Schemas
# ---------------------------------------------------------------------------

class LeadCreateSchema(Schema):
    """Fields accepted when creating a lead via POST /api/v1/contacts/leads"""

    class Meta:
        name = "LeadCreate"

    # Required
    name  = fields.Str(required=True, metadata={"description": "Full name of the contact"})
    email = fields.Email(required=True, metadata={"description": "Primary email address"})

    # Identity
    company = fields.Str(load_default="", metadata={"description": "Company or organisation name"})
    title   = fields.Str(load_default="", metadata={"description": "Job title"})
    phone   = fields.Str(load_default="", metadata={"description": "Phone number (any format)"})

    # Targeting
    brand = fields.Str(
        load_default="",
        metadata={"description": "Brand slug to associate the lead with (e.g. 'firstcityfoundry')"},
    )

    # Lead detail
    message      = fields.Str(load_default="", metadata={"description": "Free-form message or enquiry text"})
    referrer     = fields.Str(load_default="", metadata={"description": "URL or description of the referral source"})
    utm_source   = fields.Str(load_default="", metadata={"description": "UTM source parameter"})
    utm_campaign = fields.Str(load_default="", metadata={"description": "UTM campaign parameter"})
    notes        = fields.Str(load_default="", metadata={"description": "Internal notes"})
    tags         = fields.List(fields.Str(), load_default=[], metadata={"description": "List of tag strings"})

    # Social
    linkedin_url     = fields.Str(load_default="")
    twitter_handle   = fields.Str(load_default="")
    instagram_handle = fields.Str(load_default="")
    website_url      = fields.Str(load_default="")

    @validates("email")
    def validate_email_not_empty(self, value):
        if not value or not value.strip():
            raise ValidationError("Email must not be blank.")


class ContactSchema(Schema):
    """Full contact record returned by the API"""

    class Meta:
        name = "Contact"

    id           = fields.Int(dump_only=True)
    name         = fields.Str()
    email        = fields.Str()
    company      = fields.Str()
    title        = fields.Str()
    phone        = fields.Str()
    brand        = fields.Str()
    contact_type = fields.Str()
    source       = fields.Str()
    status       = fields.Str()
    message      = fields.Str()
    referrer     = fields.Str()
    utm_source   = fields.Str()
    utm_campaign = fields.Str()
    notes        = fields.Str()
    tags         = fields.List(fields.Str())
    linkedin_url     = fields.Str()
    twitter_handle   = fields.Str()
    instagram_handle = fields.Str()
    website_url      = fields.Str()
    created_at   = fields.DateTime(dump_only=True)
    updated_at   = fields.DateTime(dump_only=True)


class ContactQuerySchema(Schema):
    """Query parameters for GET /api/v1/contacts"""

    class Meta:
        name = "ContactQuery"

    brand        = fields.Str(load_default=None, metadata={"description": "Filter by brand slug"})
    contact_type = fields.Str(load_default=None, metadata={"description": "Filter by type (lead, influencer, press, …)"})
    source       = fields.Str(load_default=None, metadata={"description": "Filter by source (labs, manual, …)"})
    status       = fields.Str(load_default="active", metadata={"description": "Filter by status"})
    q            = fields.Str(load_default=None, metadata={"description": "Search name / email / company"})
    page         = fields.Int(load_default=1, validate=validate.Range(min=1))
    per_page     = fields.Int(load_default=50, validate=validate.Range(min=1, max=200))


class ContactListSchema(Schema):
    """Paginated contact list response"""

    class Meta:
        name = "ContactList"

    contacts  = fields.List(fields.Nested(ContactSchema))
    total     = fields.Int()
    page      = fields.Int()
    per_page  = fields.Int()
    pages     = fields.Int()


class ErrorSchema(Schema):
    class Meta:
        name = "APIError"

    error  = fields.Str()
    detail = fields.Str()


class LeadUpdateSchema(LeadCreateSchema):
    """Partial fields for PATCH /api/v1/contacts/<id>"""

    class Meta:
        name = "LeadUpdate"

    # Override — nothing is required for a partial update
    name  = fields.Str(load_default=None, metadata={"description": "Full name of the contact"})
    email = fields.Email(load_default=None, metadata={"description": "Primary email address"})


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@contacts_v1.route("/contacts/leads")
class LeadsResource(MethodView):
    """Create a new lead contact."""

    @contacts_v1.arguments(LeadCreateSchema, location="json")
    @contacts_v1.response(201, ContactSchema)
    @contacts_v1.alt_response(401, schema=ErrorSchema, description="Missing or invalid API key")
    @contacts_v1.alt_response(409, schema=ErrorSchema, description="Email already exists for this brand")
    @contacts_v1.doc(
        summary="Submit a lead",
        description=(
            "Creates a contact record with `contact_type=lead` and "
            "`source=labs`.  Requires scope **contacts:write**."
        ),
        security=[{"ApiKeyAuth": []}],
    )
    def post(self, lead_data: dict):
        """POST /api/v1/contacts/leads — create a lead (contacts:write)"""
        api_key = _authenticate_request("contacts:write")
        if api_key is None:
            return jsonify({"error": "Unauthorized", "detail": "Valid X-API-Key with contacts:write scope required."}), 401

        # Duplicate check within brand
        brand = lead_data.get("brand", "")
        email = lead_data["email"].strip().lower()
        existing = Contact.query.filter_by(email=email, brand=brand).first()
        if existing:
            return jsonify({
                "error": "Conflict",
                "detail": f"A contact with email '{email}' already exists for brand '{brand}'.",
                "id": existing.id,
            }), 409

        contact = Contact(
            name=lead_data["name"].strip(),
            email=email,
            company=lead_data.get("company", ""),
            title=lead_data.get("title", ""),
            phone=lead_data.get("phone", ""),
            brand=brand,
            contact_type="lead",
            source="labs",
            status="active",
            message=lead_data.get("message", ""),
            referrer=lead_data.get("referrer", ""),
            utm_source=lead_data.get("utm_source", ""),
            utm_campaign=lead_data.get("utm_campaign", ""),
            notes=lead_data.get("notes", ""),
            linkedin_url=lead_data.get("linkedin_url", ""),
            twitter_handle=lead_data.get("twitter_handle", ""),
            instagram_handle=lead_data.get("instagram_handle", ""),
            website_url=lead_data.get("website_url", ""),
        )
        contact.set_tags(lead_data.get("tags", []))

        try:
            db.session.add(contact)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception("Failed to create lead contact: %s", exc)
            return jsonify({"error": "Internal Server Error", "detail": str(exc)}), 500

        logger.info("Lead created id=%s email=%s via key=%s", contact.id, email, api_key.name)
        return contact.to_dict(), 201


@contacts_v1.route("/contacts")
class ContactsCollection(MethodView):
    """List contacts."""

    @contacts_v1.arguments(ContactQuerySchema, location="query")
    @contacts_v1.response(200, ContactListSchema)
    @contacts_v1.alt_response(401, schema=ErrorSchema, description="Missing or invalid API key")
    @contacts_v1.doc(
        summary="List contacts",
        description="Paginated contact list filtered by brand / type / source / status.  Requires scope **contacts:read**.",
        security=[{"ApiKeyAuth": []}],
    )
    def get(self, query_args: dict):
        """GET /api/v1/contacts — list contacts (contacts:read)"""
        api_key = _authenticate_request("contacts:read")
        if api_key is None:
            return jsonify({"error": "Unauthorized", "detail": "Valid X-API-Key with contacts:read scope required."}), 401

        q = Contact.query

        # Brand scoping: if the key has brand restrictions, enforce them
        allowed = api_key.get_allowed_brands()
        requested_brand = query_args.get("brand")
        if allowed:
            if requested_brand and requested_brand not in allowed:
                return jsonify({"error": "Forbidden", "detail": "API key is not allowed to access that brand."}), 403
            brands_filter = [requested_brand] if requested_brand else allowed
            q = q.filter(Contact.brand.in_(brands_filter))
        elif requested_brand:
            q = q.filter(Contact.brand == requested_brand)

        if query_args.get("contact_type"):
            q = q.filter(Contact.contact_type == query_args["contact_type"])
        if query_args.get("source"):
            q = q.filter(Contact.source == query_args["source"])
        if query_args.get("status"):
            q = q.filter(Contact.status == query_args["status"])
        if query_args.get("q"):
            like = f"%{query_args['q']}%"
            q = q.filter(
                db.or_(
                    Contact.name.ilike(like),
                    Contact.email.ilike(like),
                    Contact.company.ilike(like),
                )
            )

        page     = query_args.get("page", 1)
        per_page = query_args.get("per_page", 50)
        paginated = q.order_by(Contact.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return {
            "contacts": [c.to_dict() for c in paginated.items],
            "total":    paginated.total,
            "page":     paginated.page,
            "per_page": paginated.per_page,
            "pages":    paginated.pages,
        }, 200


@contacts_v1.route("/contacts/<int:contact_id>")
class ContactItem(MethodView):
    """Retrieve or update a single contact."""

    @contacts_v1.response(200, ContactSchema)
    @contacts_v1.alt_response(401, schema=ErrorSchema)
    @contacts_v1.alt_response(404, schema=ErrorSchema)
    @contacts_v1.doc(
        summary="Get contact",
        description="Retrieve a single contact by ID.  Requires scope **contacts:read**.",
        security=[{"ApiKeyAuth": []}],
    )
    def get(self, contact_id: int):
        """GET /api/v1/contacts/<id>"""
        api_key = _authenticate_request("contacts:read")
        if api_key is None:
            return jsonify({"error": "Unauthorized"}), 401

        contact = Contact.query.get(contact_id)
        if contact is None:
            return jsonify({"error": "Not Found"}), 404

        allowed = api_key.get_allowed_brands()
        if allowed and contact.brand not in allowed:
            return jsonify({"error": "Forbidden"}), 403

        return contact.to_dict(), 200

    @contacts_v1.arguments(LeadUpdateSchema, location="json")
    @contacts_v1.response(200, ContactSchema)
    @contacts_v1.alt_response(401, schema=ErrorSchema)
    @contacts_v1.alt_response(404, schema=ErrorSchema)
    @contacts_v1.doc(
        summary="Update contact",
        description="Partial update of a contact record.  Requires scope **contacts:write**.",
        security=[{"ApiKeyAuth": []}],
    )
    def patch(self, update_data: dict, contact_id: int):
        """PATCH /api/v1/contacts/<id>"""
        api_key = _authenticate_request("contacts:write")
        if api_key is None:
            return jsonify({"error": "Unauthorized"}), 401

        contact = Contact.query.get(contact_id)
        if contact is None:
            return jsonify({"error": "Not Found"}), 404

        allowed = api_key.get_allowed_brands()
        if allowed and contact.brand not in allowed:
            return jsonify({"error": "Forbidden"}), 403

        for field, value in update_data.items():
            if field == "tags":
                contact.set_tags(value)
            elif hasattr(contact, field):
                setattr(contact, field, value)

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": "Internal Server Error", "detail": str(exc)}), 500

        return contact.to_dict(), 200


# ---------------------------------------------------------------------------
# Health / meta endpoint (no auth required)
# ---------------------------------------------------------------------------

@contacts_v1.route("/health")
class HealthResource(MethodView):
    @contacts_v1.response(200)
    @contacts_v1.doc(summary="API health check", description="Returns 200 OK with version info. No auth required.")
    def get(self):
        """GET /api/v1/health"""
        return jsonify({"status": "ok", "version": "1.0", "api": "ForgeMarketing v1"}), 200
