import os
import json
import uuid
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import firebase_admin
from firebase_admin import credentials, firestore
import cloudinary
import cloudinary.uploader

# ── Flask ──
app = Flask(__name__, template_folder="../templates")
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("MAX_UPLOAD_SIZE_MB", "25")
) * 1024 * 1024

# ── Cloudinary Init ──
cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.environ.get("CLOUDINARY_API_KEY"),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
    secure     = True
)

# ── Firebase Init (Firestore only, no Storage) ──
def init_firebase():
    if not firebase_admin._apps:
        cred_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if cred_json:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)

init_firebase()
db = firestore.client()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    try:
        featured_ref = db.collection("photos").where("section", "==", "featured").limit(3)
        gallery_ref  = db.collection("photos").where("section", "==", "gallery")

        featured = sorted(
            [{"id": d.id, **d.to_dict()} for d in featured_ref.stream()],
            key=lambda x: x.get("uploaded_at") or "",
            reverse=True
        )[:3]

        gallery = sorted(
            [{"id": d.id, **d.to_dict()} for d in gallery_ref.stream()],
            key=lambda x: x.get("uploaded_at") or "",
            reverse=True
        )
    except Exception as e:
        print(f"INDEX ERROR: {e}")
        featured, gallery = [], []

    return render_template("index.html", featured=featured, gallery=gallery)


@app.route("/upload", methods=["POST"])
def upload():
    try:
        if "photo" not in request.files:
            flash("No file selected.", "error")
            return redirect(url_for("index"))

        file    = request.files["photo"]
        caption = request.form.get("caption", "").strip()
        section = request.form.get("section", "gallery")

        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("index"))

        if file and allowed_file(file.filename):
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                file,
                folder="couple_gallery",
                public_id=uuid.uuid4().hex,
                overwrite=False,
                resource_type="image"
            )

            public_url  = result["secure_url"]
            public_id   = result["public_id"]

            # Save metadata to Firestore
            db.collection("photos").add({
                "url":         public_url,
                "public_id":   public_id,
                "caption":     caption,
                "section":     section,
                "uploaded_at": firestore.SERVER_TIMESTAMP
            })

            flash("Photo uploaded!", "success")
        else:
            flash("Invalid file type.", "error")

    except Exception as e:
        print(f"UPLOAD ERROR: {e}")
        traceback.print_exc()
        flash(f"Upload failed: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/replace/<photo_id>", methods=["POST"])
def replace(photo_id):
    try:
        if "photo" not in request.files:
            flash("No file selected for replacement.", "error")
            return redirect(url_for("index"))

        file = request.files["photo"]
        if file.filename == "":
            flash("No file selected for replacement.", "error")
            return redirect(url_for("index"))

        if not allowed_file(file.filename):
            flash("Invalid file type.", "error")
            return redirect(url_for("index"))

        doc_ref = db.collection("photos").document(photo_id)
        doc = doc_ref.get()
        if not doc.exists:
            flash("Featured photo not found.", "error")
            return redirect(url_for("index"))

        data = doc.to_dict() or {}

        # Upload the new image first so we do not lose the existing one if upload fails
        result = cloudinary.uploader.upload(
            file,
            folder="couple_gallery",
            public_id=uuid.uuid4().hex,
            overwrite=False,
            resource_type="image"
        )

        old_public_id = data.get("public_id")
        if old_public_id:
            try:
                cloudinary.uploader.destroy(old_public_id)
            except Exception as destroy_err:
                # Keep replacement successful even if old asset cleanup fails
                print(f"CLOUDINARY DESTROY WARNING: {destroy_err}")

        doc_ref.update({
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "uploaded_at": firestore.SERVER_TIMESTAMP
        })

        flash("Featured photo replaced.", "success")
    except Exception as e:
        print(f"REPLACE ERROR: {e}")
        traceback.print_exc()
        flash(f"Replace failed: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/delete/<photo_id>", methods=["POST"])
def delete(photo_id):
    try:
        doc = db.collection("photos").document(photo_id).get()
        if doc.exists:
            data = doc.to_dict()
            # Delete from Cloudinary
            if data.get("public_id"):
                cloudinary.uploader.destroy(data["public_id"])
            # Delete from Firestore
            db.collection("photos").document(photo_id).delete()
            flash("Photo deleted.", "success")
    except Exception as e:
        print(f"DELETE ERROR: {e}")
        flash("Delete failed.", "error")

    return redirect(url_for("index"))


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_error):
    max_size_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    flash(f"Upload too large. Maximum allowed size is {max_size_mb}MB.", "error")
    return redirect(url_for("index"))
