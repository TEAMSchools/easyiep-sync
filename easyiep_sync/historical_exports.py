import argparse
import datetime
import os
import pathlib
import re
import time
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

CUSTOMER_NAME = os.getenv("CUSTOMER_NAME")
USER_NAME = os.getenv("USER_NAME")
PASSWORD = os.getenv("PASSWORD")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE")

PROJECT_DIR = pathlib.Path(__file__).absolute().parent.parent
DATA_DIR = PROJECT_DIR / "data" / CUSTOMER_NAME
BASE_URL = "https://go3.pcgeducation.com"
TARGET_FILENAME = "New NJSMART txt datamart powerschool pm-ext"

if not DATA_DIR.exists():
    DATA_DIR.mkdir(parents=True)


def get_date_range(start_date, end_date):
    for n in range(int((end_date - start_date).days + 1)):
        yield start_date + datetime.timedelta(n)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start_date", type=datetime.date.fromisoformat)
    parser.add_argument("--end_date", type=datetime.date.fromisoformat)
    args = parser.parse_args()

    eoy_date = datetime.datetime(
        year=(args.start_date.year + 1), month=6, day=30
    ).date()
    today = datetime.datetime.now(tz=ZoneInfo(LOCAL_TIMEZONE)).date()

    if args.end_date:
        end_date = args.end_date
    elif today > eoy_date:
        end_date = eoy_date
    else:
        end_date = today

    print(CUSTOMER_NAME)
    print(f"{args.start_date} - {end_date}")

    easyiep = requests.Session()

    login_url = f"{BASE_URL}/easyiep.plx"
    login_params = {"op": "login", "CustomerName": CUSTOMER_NAME}
    login_payload = {"Name": USER_NAME, "Password": PASSWORD}

    print("Logging into EasyIEP...")
    r_login = easyiep.post(url=login_url, params=login_params, data=login_payload)
    r_login.raise_for_status()

    session_id = parse_qs(urlparse(r_login.url).query).get("SessionID", [])[0]
    report_params = {
        "op": "doreport",
        "CustomerName": CUSTOMER_NAME,
        "SessionID": session_id,
    }

    for date in get_date_range(args.start_date, end_date):
        download_filepath = (
            DATA_DIR / f"NJSMART-PowerSchool-{date.strftime(r'%Y%m%d')}.txt"
        )

        if download_filepath.exists():
            continue

        print(date)
        date_fmt = date.strftime(r"%Y-%m-%d")

        report_url = f"{BASE_URL}/easyiep.plx"
        report_payload = {
            "ReportID": 55,
            "Preview": None,
            "lVarsToSave": date_fmt,
            "orgReferenceDate": date_fmt,
            "ReferenceDate": date_fmt,
            "SelectSchool": 1,
            "SelectCaseManager": 1,
            "SelectCurrentIEPDates": 1,
            "SelectRespDistrict": 1,
            "Submit": "Generate Report",
        }

        print("\tExecuting report...")
        run_date = datetime.datetime.now(tz=ZoneInfo(LOCAL_TIMEZONE))
        r_report = easyiep.post(
            url=report_url, params=report_params, data=report_payload
        )
        r_report.raise_for_status()

        retrieval_url = f"{BASE_URL}/easyiep.plx"
        retrieval_params = {
            "op": "Reports.htm",
            "PageLabel": "Reports",
            "CustomerName": CUSTOMER_NAME,
            "SessionID": session_id,
        }

        report_incomplete = True

        while report_incomplete:
            print("\tChecking for completed report...")
            r_retrieval = easyiep.post(url=retrieval_url, params=retrieval_params)
            r_retrieval.raise_for_status()

            soup = BeautifulSoup(r_retrieval.text, "html.parser")
            all_a = soup.find_all("a")
            target_a = [
                a.attrs["href"]
                for a in all_a
                if TARGET_FILENAME in str(a.string) and "viewdoc" in a.attrs["href"]
            ]

            for a in target_a:
                file_name = parse_qs(urlparse(a).query)["file"][0]
                timestamp_search = re.search(
                    r"(\d+-\d+-\d+-\d+!\d+-\d+-\d+)", file_name
                )
                file_timestamp_str = timestamp_search.group(1)
                file_timestamp = datetime.datetime.strptime(
                    file_timestamp_str, r"%H-%M-%S-%f!%m-%d-%y"
                ).replace(tzinfo=ZoneInfo(LOCAL_TIMEZONE))

                if file_timestamp >= run_date:
                    download_url = f"{BASE_URL}{a}"

                    print(f"\tDownloading report {a}...")
                    r_download = easyiep.post(url=download_url)
                    r_download.raise_for_status()

                    print("\tSaving report...")
                    with download_filepath.open("w+") as f:
                        f.write(r_download.text)

                    report_incomplete = False

            time.sleep(30)


if __name__ == "__main__":
    main()
