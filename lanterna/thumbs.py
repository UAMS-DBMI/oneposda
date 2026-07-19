#!/usr/bin/python3 -u
import redis
import subprocess
import os
import signal

REDIS_HOST=os.environ['POSDA_REDIS_HOST']

# Convert SIGTERM into an exception
class SigTerm(SystemExit): 
    pass

def termhandler(a, b):
    raise SigTerm(1)

signal.signal(signal.SIGTERM, termhandler)


def main():

    # socket_timeout must exceed the brpop block time below, or every
    # empty poll times out at the socket layer (redis-py >= 8 defaults
    # socket_timeout to 5s)
    redis_db = redis.StrictRedis(host=REDIS_HOST, db=0, socket_timeout=10)

    while True:
        sr = redis_db.brpop("thumbnails_required", 5)

        if sr is None:
            continue

        _, filename = sr
        print(filename)

        subprocess.run(["dcm2jpg",
                        filename,
                        f"{filename.decode()}[512;512;-1][0].jpeg"])


if __name__ == "__main__":
    print("thumbs, a lightweight thumbnail generator")
    print(f"{REDIS_HOST=}")
    main()
