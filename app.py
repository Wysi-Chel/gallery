import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, firestore, storage

app = Flask(__name__)
app.secret_key = "your-secret-key-change-this"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# Download your service account key from Firebase Console:
# Project Settings → Service Accounts → Generate New Private Key
# Save it as "serviceAccountKey.json" in this folder
cred = credentials.Certificate("import json
cred_dict = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
cred = credentials.Certificate(cred_dict)")
firebase_admin.initialize_app(cred, {
    # Replace with your actual bucket (Firebase Console → Storage)
    "storageBucket": "YOUR_PROJECT_ID.appspot.com"
})

db = firestore.client()
bucket = storage.bucket()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    featured_ref = db.collection("photos").where("section", "==", "featured").order_by(
        "uploaded_at", direction=firestore.Query.DESCENDING).limit(3)
    gallery_ref = db.collection("photos").where("section", "==", "gallery").order_by(
        "uploaded_at", direction=firestore.Query.DESCENDING)

    featured = [{"id": d.id, **d.to_dict()} for d in featured_ref.stream()]
    gallery   = [{"id": d.id, **d.to_dict()} for d in gallery_ref.stream()]

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

        # Upload image to Firebase Storage
        blob = bucket.blob(f"photos/{filename}")
        blob.upload_from_file(file, content_type=file.content_type)
        blob.make_public()
        public_url = blob.public_url

        # Save metadata to Firestore
        db.collection("photos").add({
            "filename":    filename,
            "url":         public_url,
            "caption":     caption,
            "section":     section,
            "uploaded_at": firestore.SERVER_TIMESTAMP
        })

        flash("Photo uploaded!", "success")
    else:
        flash("Invalid file type. Use JPG, PNG, GIF, or WEBP.", "error")

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


if __name__ == "__main__":
    app.run(debug=True)