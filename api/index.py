import os
import json
import uuid
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, firestore
import cloudinary
import cloudinary.uploader

# ── Flask ──
app = Flask(__name__, template_folder="../templates")
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

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