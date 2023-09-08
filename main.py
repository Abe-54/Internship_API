from datetime import datetime, timedelta
from email.mime.text import MIMEText
import queue
import smtplib
from flask import Flask, Response, jsonify
from flask_apscheduler import APScheduler
from flask_cors import CORS
import requests
import json
import os
import resend

TEST_MODE = False  # Set to True to use mock JSON file for testing

app = Flask(__name__)
resend.api_key = "re_4xqsTDGK_AjPwBCJ77WVuSAE2E3bHrSSq"
CORS(app)

scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()

# Global variables to store new and removed internships
new_internships = {}
removed_internships = {}
url = "https://raw.githubusercontent.com/SimplifyJobs/Summer2024-Internships/dev/.github/scripts/listings.json"
local_file_path = "internships/local_listings.json"
mock_file_path = "internships/mock_listings.json"  # Mock JSON file for testing

# Flask routes


@app.route("/new_internships", methods=["GET"])
def get_new_internships():
    print(read_local_json("new_internships_last_24_hours.json"))
    return jsonify(read_local_json("new_internships_last_24_hours.json"))

# Flask route to get removed internships from the last 24 hours


@app.route("/removed_internships", methods=["GET"])
def get_removed_internships():
    print(read_local_json("removed_internships_last_24_hours.json"))
    return jsonify(read_local_json("removed_internships_last_24_hours.json"))


@app.route("/all_internships", methods=["GET"])
def get_all_internships():
    print("Internships Found: " + len(fetch_json(url)))
    return jsonify(fetch_json(url))


@app.route("/all_summer_internships", methods=["GET"])
def all_summer_internships():
    return get_all_summer_internships()


@app.route("/")
def index():
    return "Internship Tracker is running"

# Function to fetch JSON data from a URL


def fetch_json(url):
    response = requests.get(url)
    return json.loads(response.text) if response.status_code == 200 else None


def convert_to_html_bulleted_list(internships):
    return '<ul>' + ''.join([f"<li>{internship['title']} at {internship['company_name']}</li>" for internship in internships]) + '</ul>'


def send_email(subject, internships):
    """Send an email notification using resend."""
    body = convert_to_html_bulleted_list(internships)
    params = {
        "from": "Internship Tracker <onboarding@resend.dev>",
        "to": ["a.rubio1224@gmail.com"],
        "subject": subject,
        "html": body,
        "headers": {
            "X-Entity-Ref-ID": "123456789"
        }
    }

    email = resend.Emails.send(params)
    print(email)

# Function to read local JSON file


def read_local_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)


# Function to write data to a local JSON file
def write_local_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


# Function to convert dictionary to tuple
def convert_dict_to_tuple(d):
    return tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(d.items()))


@scheduler.task("cron", id="check_github_changes", second="*/5")
# Function to check for changes in GitHub data
def check_github_changes():
    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
    print("Checking for changes...\n")

    latest_data = fetch_json(
        url) if not TEST_MODE else read_local_json(mock_file_path)
    local_data = read_local_json(
        local_file_path) if os.path.exists(local_file_path) else []

    # Filter internships for the term "Summer 2024"
    latest_data_filtered = {convert_dict_to_tuple(
        d) for d in latest_data if "Summer 2024" in d["terms"]}
    local_data_filtered = {convert_dict_to_tuple(
        d) for d in local_data if "Summer 2024" in d["terms"]}

    new_internships = [dict(t)
                       for t in latest_data_filtered - local_data_filtered]
    removed_internships = [dict(t)
                           for t in local_data_filtered - latest_data_filtered]

    current_time = datetime.now()
    last_24_hours = current_time - timedelta(days=1)

    if new_internships:
        for internship in new_internships:
            internship["timestamp"] = current_time.isoformat()
        recent_new_internships = [i for i in new_internships if datetime.fromisoformat(
            i["timestamp"]) > last_24_hours]
        write_local_json("internships/new_internships_last_24_hours.json",
                         recent_new_internships)
        print("NEW INTERNSHIPS: ", recent_new_internships)
        send_email("New Internships Added", new_internships)

    if removed_internships:
        for internship in removed_internships:
            internship["timestamp"] = current_time.isoformat()
        recent_removed_internships = [
            i for i in removed_internships if datetime.fromisoformat(i["timestamp"]) > last_24_hours]
        write_local_json("internships/removed_internships_last_24_hours.json",
                         recent_removed_internships)
        print("REMOVED INTERNSHIPS: ", recent_removed_internships)
        send_email("Internships Removed", removed_internships)

    # Update the local data
    write_local_json(local_file_path, latest_data)

    if not new_internships and not removed_internships:
        print("No changes detected.")


@scheduler.task("cron", id="clear_json_files", hour=8)
def clear_json_files():
    empty_list = []
    write_local_json("new_internships_last_24_hours.json", empty_list)
    write_local_json("removed_internships_last_24_hours.json", empty_list)
    print("Cleared JSON files.")


def get_all_summer_internships():
    all_internships = fetch_json(url)
    print(f"Fetched {len(all_internships)} internships.")  # Debug line

    if all_internships is None:
        print("No internships fetched.")  # Debug line
        return jsonify([])

    summer_internships = [
        internship for internship in all_internships if "Summer 2024" in internship.get("terms", [])]

    # Debug line
    print(f"Filtered {len(summer_internships)} summer internships.")
    return jsonify(summer_internships)


if __name__ == "__main__":
    app.run()
