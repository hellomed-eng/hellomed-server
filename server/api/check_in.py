import requests
import flask
import server
from datetime import datetime, date
from zoneinfo import ZoneInfo

from server.api.check_in_helpers import (
    build_insert_row,
    resolve_form_type,
    validate_check_in_body,
)

INSERT_CHECK_IN_SQL = """
        INSERT INTO check_ins (
        formType,
        name,
        birthDate,
        phone,
        email,
        hearAboutUs,
        address,
        zipcode,
        medicationAllergy,
        preferredPharmacy,
        homeMedication,
        reasonForVisit,
        exposures,
        recentTests,
        recentVisits,
        idImage,
        insuranceImageFront,
        insuranceImageBack,
        medicalHistoryChanged,
        medicalHistoryDescription,
        medicationsChanged,
        medicationsList,
        medicationAllergyType)
        VALUES (
        %(formType)s,
        %(name)s,
        %(birthDate)s,
        %(phone)s,
        %(email)s,
        %(hearAboutUs)s,
        %(address)s,
        %(zipcode)s,
        %(medicationAllergy)s,
        %(preferredPharmacy)s,
        %(homeMedication)s,
        %(reasonForVisit)s,
        %(exposures)s,
        %(recentTests)s,
        %(recentVisits)s,
        %(idImage)s,
        %(insuranceImageFront)s,
        %(insuranceImageBack)s,
        %(medicalHistoryChanged)s,
        %(medicalHistoryDescription)s,
        %(medicationsChanged)s,
        %(medicationsList)s,
        %(medicationAllergyType)s)
        """


def _format_check_in_for_emit(check_in_to_emit):
    if not check_in_to_emit:
        return check_in_to_emit

    if isinstance(check_in_to_emit.get("birthDate"), date):
        birth_date_dt = datetime.combine(
            check_in_to_emit["birthDate"], datetime.min.time()
        )
        birth_date_dt = birth_date_dt.replace(tzinfo=ZoneInfo("UTC"))
        check_in_to_emit["birthDate"] = birth_date_dt.strftime("%Y-%m-%d %Z")

    if isinstance(check_in_to_emit.get("created_at"), datetime):
        if check_in_to_emit["created_at"].tzinfo is None:
            check_in_to_emit["created_at"] = check_in_to_emit["created_at"].replace(
                tzinfo=ZoneInfo("UTC")
            )
        check_in_to_emit["created_at"] = check_in_to_emit["created_at"].strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )

    return check_in_to_emit


REVIEW_AUTOMATION_URL = "https://autoreviewrequest.vercel.app/api/checkin"
def _lookup_phone_on_file(name, birth_date):
    """
    Best-effort lookup of a phone number from this patient's most recent
    prior check-in, used when a returning patient doesn't retype their
    phone number (it's optional on that form).
    """
    if not name or not birth_date:
        return None
    cursor = server.model.Cursor()
    cursor.execute(
        """
        SELECT phone
        FROM check_ins
        WHERE name = %(name)s
          AND birthDate = %(birthDate)s
          AND phone IS NOT NULL
          AND phone != ''
        ORDER BY id DESC
        LIMIT 1
        """,
        {"name": name, "birthDate": birth_date},
    )
    row = cursor.fetchone()
    return row["phone"] if row else None

def trigger_review_automation(name, phone):
    """
    Fire-and-forget call to the review-request automation. Wrapped in
    try/except so a failure here never breaks the actual check-in submission.
    Only sends name/phone — no clinical data.
    """
    if not name or not phone:
        server.application.logger.warning(
            f"Review automation skipped: missing name or phone "
            f"(has_name={bool(name)}, has_phone={bool(phone)})"
        )
        return
    try:
        resp = requests.post(
            REVIEW_AUTOMATION_URL,
            json={"name": name, "phone": phone},
            timeout=3,
        )
        if resp.status_code >= 400:
            server.application.logger.warning(
                f"Review automation call returned {resp.status_code}: {resp.text}"
            )
    except Exception as e:
        server.application.logger.warning(f"Review automation call failed: {e}")


@server.application.route("/api/v1/check-in/", methods=["POST"])
def post_check_in():
    """
    Intake body from POST request and insert into database.

    Requires formType (or form_type): 'new' | 'returning'. This is the only
    way to distinguish check-in variants.
    """
    body = flask.request.json or {}
    form_type = resolve_form_type(body)
    if form_type is None:
        return flask.jsonify(
            {
                "error": "formType is required and must be 'new' or 'returning'",
            }
        ), 400

    validation_error = validate_check_in_body(body, form_type)
    if validation_error:
        return flask.jsonify({"error": validation_error}), 400

    row = build_insert_row(body, form_type)
    cursor = server.model.Cursor()
    cursor.execute(INSERT_CHECK_IN_SQL, row)
    inserted_check_in_id = cursor.lastrowid()

    cursor.execute(
        """
        SELECT
        id,
        formType,
        name,
        birthDate,
        email,
        reasonForVisit,
        created_at,
        viewed
        FROM check_ins
        WHERE id = %(id)s
        """,
        {"id": inserted_check_in_id},
    )
    check_in_to_emit = _format_check_in_for_emit(cursor.fetchone())

    server.sio.emit("new-checkin", check_in_to_emit)

    phone_for_review = body.get("phone")
    if isinstance(phone_for_review, str) and phone_for_review.strip() == "":
        phone_for_review = None
    if phone_for_review is None:
        phone_for_review = _lookup_phone_on_file(body.get("name"), body.get("birthDate"))

    trigger_review_automation(body.get("name"), phone_for_review)

    return flask.jsonify({"id": inserted_check_in_id, "formType": row["formType"]}), 200


@server.application.route("/api/v1/check-in/", methods=["GET"])
def get_check_ins():
    """
    Get submitted check-ins by page and size. Size per page is defaulted to 20.
    """
    size = flask.request.args.get("size", default=15, type=int)
    page = flask.request.args.get("page", default=0, type=int)

    if page < 0:
        return flask.jsonify({"error": "invalid pagination args"}), 400

    cursor = server.model.Cursor()
    cursor.execute(
        """
        SELECT
        id,
        formType,
        name,
        birthDate,
        email,
        reasonForVisit,
        created_at,
        viewed
        FROM check_ins
        ORDER BY id DESC LIMIT %(limit)s OFFSET %(offset)s
        """,
        {"limit": size, "offset": page * size},
    )
    check_ins = cursor.fetchall()

    if not check_ins:
        return flask.jsonify({"error": "No check-ins in requested page"}), 404

    cursor.execute("SELECT COUNT(*) AS total_count FROM check_ins", {})
    total_count = cursor.fetchone()["total_count"]

    response = {"checkIns": check_ins, "totalCheckIns": total_count}

    return flask.jsonify(response), 200


@server.application.route("/api/v1/check-in/<int:id>/", methods=["GET"])
def get_check_in(id):
    cursor = server.model.Cursor()
    cursor.execute(
        """
        SELECT * FROM check_ins
        WHERE id = %(id)s
        """,
        {"id": id},
    )
    check_in = cursor.fetchone()

    if check_in and not check_in["viewed"]:
        cursor.execute(
            """
            UPDATE check_ins
            SET viewed = 1
            WHERE id = %(id)s
            """,
            {"id": id},
        )

    return flask.jsonify(check_in), 200


@server.application.route("/api/v1/check-in/<int:id>/", methods=["PATCH"])
def patch_check_in(id):
    flag_to_update = flask.request.json
    cursor = server.model.Cursor()
    cursor.execute(
        f"""
        UPDATE check_ins
        SET {flag_to_update} = false
        WHERE id = %(id)s
        """,
        {"id": id},
    )
    return flask.jsonify({"Success": True}), 200
