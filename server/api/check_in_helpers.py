"""Helpers for check-in POST normalization and validation."""

VALID_FORM_TYPES = ("new", "returning")

REQUIRED_NEW = (
    "name",
    "birthDate",
    "phone",
    "email",
    "hearAboutUs",
    "address",
    "zipcode",
    "reasonForVisit",
    "preferredPharmacy",
)

REQUIRED_RETURNING = (
    "name",
    "birthDate",
    "phone",
    "reasonForVisit",
    "medicalHistoryChanged",
    "medicationsChanged",
    "medicationAllergyType",
)


def _empty_to_none(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def resolve_form_type(body: dict):
    """
    Return 'new' | 'returning' when formType is valid, else None.
    formType is the only supported discriminator.
    """
    explicit = body.get("formType") or body.get("form_type")
    if explicit in VALID_FORM_TYPES:
        return explicit
    return None


def _require_fields(body: dict, fields: tuple, label: str):
    missing = [f for f in fields if not _empty_to_none(body.get(f))]
    if missing:
        return f"{label} check-in missing required fields: {', '.join(missing)}"
    return None


def validate_check_in_body(body: dict, form_type: str):
    if form_type == "new":
        return _require_fields(body, REQUIRED_NEW, "New patient")

    err = _require_fields(body, REQUIRED_RETURNING, "Returning patient")
    if err:
        return err

    if body.get("medicalHistoryChanged") == "yes" and not _empty_to_none(
        body.get("medicalHistoryDescription")
    ):
        return (
            "Returning check-in requires medicalHistoryDescription "
            "when medicalHistoryChanged is yes"
        )

    if body.get("medicationsChanged") == "yes" and not _empty_to_none(
        body.get("medicationsList")
    ):
        return (
            "Returning check-in requires medicationsList "
            "when medicationsChanged is yes"
        )

    if body.get("medicationAllergyType") == "yes" and not _empty_to_none(
        body.get("medicationAllergy")
    ):
        return (
            "Returning check-in requires medicationAllergy "
            "when medicationAllergyType is yes"
        )

    return None


def build_insert_row(body: dict, form_type: str) -> dict:
    if form_type == "new":
        return {
            "formType": form_type,
            "name": body.get("name"),
            "birthDate": body.get("birthDate"),
            "phone": _empty_to_none(body.get("phone")),
            "email": _empty_to_none(body.get("email")),
            "hearAboutUs": _empty_to_none(body.get("hearAboutUs")),
            "address": _empty_to_none(body.get("address")),
            "zipcode": _empty_to_none(body.get("zipcode")),
            "medicationAllergy": _empty_to_none(body.get("medicationAllergy")),
            "preferredPharmacy": _empty_to_none(body.get("preferredPharmacy")),
            "homeMedication": _empty_to_none(body.get("homeMedication")),
            "reasonForVisit": body.get("reasonForVisit"),
            "exposures": _empty_to_none(body.get("exposures")),
            "recentTests": _empty_to_none(body.get("recentTests")),
            "recentVisits": _empty_to_none(body.get("recentVisits")),
            "idImage": bool(body.get("idImage", False)),
            "insuranceImageFront": bool(body.get("insuranceImageFront", False)),
            "insuranceImageBack": bool(body.get("insuranceImageBack", False)),
            "medicalHistoryChanged": None,
            "medicalHistoryDescription": None,
            "medicationsChanged": None,
            "medicationsList": None,
            "medicationAllergyType": None,
        }

    return {
        "formType": form_type,
        "name": body.get("name"),
        "birthDate": body.get("birthDate"),
        "phone": _empty_to_none(body.get("phone")),
        "email": _empty_to_none(body.get("email")),
        "hearAboutUs": None,
        "address": _empty_to_none(body.get("address")),
        "zipcode": None,
        "medicationAllergy": _empty_to_none(body.get("medicationAllergy")),
        "preferredPharmacy": _empty_to_none(body.get("preferredPharmacy")),
        "homeMedication": None,
        "reasonForVisit": body.get("reasonForVisit"),
        "exposures": None,
        "recentTests": None,
        "recentVisits": None,
        "idImage": bool(body.get("idImage", False)),
        "insuranceImageFront": bool(body.get("insuranceImageFront", False)),
        "insuranceImageBack": bool(body.get("insuranceImageBack", False)),
        "medicalHistoryChanged": _empty_to_none(body.get("medicalHistoryChanged")),
        "medicalHistoryDescription": _empty_to_none(
            body.get("medicalHistoryDescription")
        ),
        "medicationsChanged": _empty_to_none(body.get("medicationsChanged")),
        "medicationsList": _empty_to_none(body.get("medicationsList")),
        "medicationAllergyType": _empty_to_none(body.get("medicationAllergyType")),
    }
