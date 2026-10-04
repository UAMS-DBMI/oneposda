#!/usr/bin/python3 -u
ABOUT="""\

This program submits new files to the NBIA submitDICOM API.

See the interface at: https://github.com/CBIIT/NBIA-TCIA/blob/master/software/nbia-api/src/gov/nih/nci/nbia/restAPI/DICOMSubmission.java

"""

import redis
import json
import sys
import time
import os
from typing import NamedTuple

import requests
import psycopg2


URL=os.environ['REAM_URL']
USER=os.environ['REAM_USER']
PASS=os.environ['REAM_PASS']
CLIENTID=os.environ['REAM_CLIENTID']
CLIENTSECRET=os.environ['REAM_CLIENTSECRET']
RETRY_COUNT=int(os.environ['REAM_RETRY_COUNT'])
PSQL_DB_NAME=os.environ['REAM_PSQL_DB_NAME']
OVERWRITE=os.environ.get('REAM_OVERWRITE')
REDIS_HOST=os.environ['POSDA_REDIS_HOST']

TOKEN=None

class LoginFailedError(RuntimeError): pass
class LoginExpiredError(RuntimeError): pass
class SubmitFailedError(RuntimeError): pass

class File(NamedTuple):
    subprocess_invocation_id: int
    file_id: int
    collection: str
    site: str
    site_id: int
    batch: int
    filename: str
    third_party_analysis_url: str


class Db:
    """Postgres connection holder that can reconnect on a dropped connection."""

    RECONNECT_DEADLINE_SECONDS = 300

    def __init__(self, dbname):
        self.dbname = dbname
        self.conn = None
        self.cur = None
        self._connect()

    def _connect(self):
        self.conn = psycopg2.connect(dbname=self.dbname)
        self.conn.autocommit = True
        self.cur = self.conn.cursor()

    def reconnect_or_die(self):
        for c in (self.cur, self.conn):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
        self.cur = None
        self.conn = None

        start = time.monotonic()
        delay = 1
        while True:
            try:
                self._connect()
                print("reconnected to postgres")
                return
            except psycopg2.OperationalError as e:
                elapsed = time.monotonic() - start
                if elapsed >= self.RECONNECT_DEADLINE_SECONDS:
                    print(f"could not reconnect to postgres after {elapsed:.0f}s, exiting")
                    sys.exit(1)
                print(f"reconnect failed ({e}), retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)


def main_loop(redis_db, db):
    while True:
        sr = redis_db.brpop("submission_required", 5)
        if sr is None:
            continue

        _, value = sr
        file = File(*json.loads(value))
        try:
            submit_file(file)
            set_file_status(db, file, success=True)
        except SubmitFailedError as e:
            # probably should put this onto a failed-file list now?
            print(e)
            set_file_status(db, file, success=False, error=e)

def set_file_status(db, file, success=True, error=None):
    sql = """
        insert into public_copy_status
        values (%s, %s, %s, %s)
    """
    params = [file.subprocess_invocation_id, file.file_id, success, str(error)]
    for _ in range(3):
        try:
            db.cur.execute(sql, params)
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"postgres connection lost ({e}), reconnecting")
            db.reconnect_or_die()
        except Exception as e:
            print(e)
            return
    print(f"set_file_status: gave up on file_id={file.file_id} after repeated connection failures")

def submit_file(f):
    """Submit the file, try several times before giving up"""
    global TOKEN

    errors = []
    for i in range(RETRY_COUNT):
        try:
            return _submit_file(f)
        except SubmitFailedError as e:
            errors.append(e)
        except requests.exceptions.ConnectionError as e:
            errors.append(e)
            print("WAIT: Server rejected connection, waiting 1 second for retry...")
            time.sleep(1)  # wait a bit for the server to get over it's funk
        except LoginExpiredError:
            TOKEN = login_to_api()
        except Exception as e:
            errors.append(e)

    raise SubmitFailedError(("Failed to submit the file; error details follow", f, errors))


def _submit_file(f):
    tpa_url = f.third_party_analysis_url

    if tpa_url is None:
        tpa_url = ''

    if len(tpa_url) > 0:
        tpa = "yes"
    else:
        tpa = "NO"

    # note that if unset on the REST call, overwrite is the default
    if OVERWRITE is None:
        overwrite = "NO"
    else:
        overwrite = "YES"


    payload = {'project': f.collection,
               'siteName': f.site,
               'siteID': f.site_id,
               'batch': f.batch,
               'uri': f.filename,
               'thirdPartyAnalysis': tpa,
               'descriptionURI': tpa_url,
               'posdaTransferId': f.file_id,
               'overwrite': overwrite,
               }
    headers = {
        "Authorization": "Bearer {}".format(TOKEN),
    }
    req = requests.post(URL + "/nbia-api/services/submitDICOM", headers=headers, data=payload)

    if req.status_code == 200:
        print(f.filename)
        return
    elif req.status_code == 401:
        print(req.content)
        if req.content == b'Insufficiant Privileges' \
                or b'Unauthorized' in req.content:
            raise LoginExpiredError()
        # indicates an acess error, generally an expired token
        try:
            message = req.json()
        except:
            # if it wasn't json at all, just report it?
            raise SubmitFailedError(req.content)
        if message['error'] == "invalid_token":
            raise LoginExpiredError()
        else:
            raise SubmitFailedError(req.content)
    else:
        raise SubmitFailedError((req.status_code, req.content))

def login_to_api():
    payload = {'username': USER,
               'password': PASS,
               'client_id': CLIENTID,
               'client_secret': CLIENTSECRET,
               'grant_type': 'password',
               }
    req = requests.post(URL + "/nbia-api/oauth/token", data=payload)

    if req.status_code == 200:
        obj = req.json()
        return obj['access_token']
    else:
        raise LoginFailedError(req.content)

def login_or_die():
    for i in range(10):
        try:
            return login_to_api()
        except LoginFailedError as e:
            print(e)
            time.sleep(1)

    raise LoginFailedError("Login failed too many times, see previous errors!")

def main():
    global TOKEN

    print("ream, starting up...")

    # socket_timeout must exceed the brpop block time below, or every
    # empty poll times out at the socket layer (redis-py >= 8 defaults
    # socket_timeout to 5s)
    redis_db = redis.StrictRedis(host=REDIS_HOST, db=0, socket_timeout=10)
    print("connected to redis")

    db = Db(PSQL_DB_NAME)
    print("connected to postgres")


    TOKEN = login_or_die()
    print(f"logged in to api, token={TOKEN}")

    main_loop(redis_db, db)



if __name__ == "__main__":
    main()
