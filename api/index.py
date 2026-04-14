import os
import json
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, firestore, storage

app = Flask(__name__, template_folder="../templates")

app.secret_key = "your-secret-key-change-this"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

if not firebase_admin._apps:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
        cred_dict = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("serviceAccountKey.json")

    firebase_admin.initialize_app(cred, {
        "storageBucket": "prj_Ixulp52EKXuuU9TkI3zub9WLVhEn.appspot.com"
    })

db = firestore.client()
bucket = storage.bucket()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
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

    return render_template("index.html", featured=featured, gallery=gallery)


@app.route("/upload", methods=["POST"])
def upload():
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

    return redirect(url_for("index"))


@app.route("/delete/<photo_id>", methods=["POST"])
def delete(photo_id):
    doc = db.collection("photos").document(photo_id).get()
    if doc.exists:
        data = doc.to_dict()
        blob = bucket.blob(f"photos/{data['filename']}")
        if blob.exists():
            blob.delete()
        db.collection("photos").document(photo_id).delete()
        flash("Photo deleted.", "success")
    return redirect(url_for("index"))

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
        flash(f"Upload failed: {str(e)}", "error")

    return redirect(url_for("index"))