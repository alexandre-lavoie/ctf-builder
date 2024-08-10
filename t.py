import json

from ctf_builder.models.challenge import Track


with open("sample/challenges/deploy/challenge.json") as h:
    data = json.load(h)

print(Track.parse(data))
