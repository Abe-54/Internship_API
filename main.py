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

TEST_MODE = False  # Set to True to use mock JSON file for testing

app = Flask(__name__)
CORS(app)

scheduler = APScheduler()
scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()

# Global variables to store new and removed internships
new_internships = {}
removed_internships = {}
url = "https://raw.githubusercontent.com/SimplifyJobs/Summer2024-Internships/dev/.github/scripts/listings.json"
local_file_path = "local_listings.json"
mock_file_path = "mock_listings.json"  # Mock JSON file for testing

# Email configuration
SMTP_SERVER = "smtp.resend.com"  # Use your SMTP server
SMTP_PORT = 587
SMTP_USERNAME = "resend"  # Your email
SMTP_PASSWORD = "re_4xqsTDGK_AjPwBCJ77WVuSAE2E3bHrSSq"  # Your password
RECIPIENT_EMAIL = "a.rubio1224@gmail.com"  # Email to receive notifications

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
    if TEST_MODE:
        return read_local_json(mock_file_path)
    else:
        response = requests.get(url)
        if response.status_code == 200:
            try:
                return json.loads(response.text)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {e}")
                return None
        else:
            print("Failed to fetch data.")
            return None


def send_email(subject, body):
    """Send an email notification."""
    msg = MIMEText(body)
    msg['From'] = SMTP_USERNAME
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = subject

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        status_code, response = server.ehlo()
        print(f"[*] Echoing the server: {status_code} {response}")

        server.starttls()
        print(f"[*] Starting TLS Connection...: {status_code} {response}")

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("[*] Logged in successfully: {status_code} {response}")

        server.sendmail(SMTP_USERNAME, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

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
    print("Checking for changes...\n")

    global new_internships, removed_internships

    current_time = datetime.now()

    latest_data = fetch_json(url)

    if os.path.exists(local_file_path):
        local_data = read_local_json(local_file_path)

        if local_data != latest_data:
            print("Changes detected!\n")

            scheduler.pause()

            # Filter internships for the term "Summer 2024"
            latest_data_filtered = [
                d for d in latest_data if "Summer 2024" in d["terms"]]
            local_data_filtered = [
                d for d in local_data if "Summer 2024" in d["terms"]]

            # Convert dictionaries to sets of tuples for comparison
            latest_data_set = {convert_dict_to_tuple(
                d) for d in latest_data_filtered}
            local_data_set = {convert_dict_to_tuple(
                d) for d in local_data_filtered}

            # Find new internships
            new_internships = [dict(t)
                               for t in latest_data_set - local_data_set]

            # Find removed internships
            removed_internships = [dict(t)
                                   for t in local_data_set - latest_data_set]

            # Find and save new internships
            if len(new_internships) > 0:
                for internship in new_internships:
                    internship["timestamp"] = current_time.isoformat()

                # Filter and write internships from the last 24 hours
                last_24_hours = current_time - timedelta(days=1)
                recent_new_internships = [i for i in new_internships if datetime.fromisoformat(
                    i["timestamp"]) > last_24_hours]
                write_local_json(
                    "new_internships_last_24_hours.json", recent_new_internships)
                print("NEW INTERNSHIPS: ", recent_new_internships, "\n")
                send_email("New Internships Added",
                           f"New internships: {recent_new_internships}")

            # Find and save removed internships
            if len(removed_internships) > 0:
                for internship in removed_internships:
                    internship["timestamp"] = current_time.isoformat()

                # Filter and write removed internships from the last 24 hours
                last_24_hours = current_time - timedelta(days=1)
                recent_removed_internships = [
                    i for i in removed_internships if datetime.fromisoformat(i["timestamp"]) > last_24_hours]
                write_local_json(
                    "removed_internships_last_24_hours.json", recent_removed_internships)
                print("REMOVED INTERNSHIPS: ", recent_removed_internships, "\n")
                send_email("Internships Removed",
                           f"Removed internships: {recent_removed_internships}")

            # Update the local data
            write_local_json(local_file_path, latest_data)
            scheduler.resume()
        else:
            print("No changes detected.\n")


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
    send_email("New Internships Added",
               f"New internships: test")
    app.run()
