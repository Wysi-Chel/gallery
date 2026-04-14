import os
import json
import uuid
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ── Flask app — must be top-level for Vercel ──
app = Flask(__name__, template_folder="../templates")
app.secret_key = "mygallery2026-supersecret-xyz789"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# ── Firebase Init ──
def init_firebase():
    if not firebase_admin._apps:
        cred_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if cred_json:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate("serviceAccountKey.json")

        bucket_name = os.environ.get("FIREBASE_BUCKET", "gallery-7c513.appspot.com")
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})

init_firebase()
db = firestore.client()
bucket = storage.bucket()


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
            ext      = file.filename.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            blob = bucket.blob(f"photos/{filename}")
            blob.upload_from_file(file, content_type=file.content_type)
            blob.make_public()
            public_url = blob.public_url

            db.collection("photos").add({
                "filename":    filename,
                "url":         public_url,
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
            blob = bucket.blob(f"photos/{data['filename']}")
            if blob.exists():
                blob.delete()
            db.collection("photos").document(photo_id).delete()
            flash("Photo deleted.", "success")
    except Exception as e:
        print(f"DELETE ERROR: {e}")
        flash("Delete failed.", "error")

    return redirect(url_for("index"))