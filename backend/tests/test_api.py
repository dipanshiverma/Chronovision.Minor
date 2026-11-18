"""Full-stack tests through the real pipeline with a SCRIPTED detector (synthetic theft scenario)."""
import cv2
import numpy as np

from app import detector as det
from app.events import TrackObs
from app.pipeline import process_video

W, H, FPS, SECONDS = 640, 360, 20, 14


def make_video(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for i in range(FPS * SECONDS):
        f = np.full((H, W, 3), 90, np.uint8)
        cv2.putText(f, str(i), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        vw.write(f)
    vw.release()


def person(tid, cx, conf=0.9):
    return TrackObs(tid, (cx - 22, 150, cx + 22, 290), conf, "person", "person")


class TheftScript:
    """Victim stands at x=130 holding a handbag. A second person walks up at t=3-6, takes it and runs away."""
    def start_video(self): self.n = 0
    def track(self, frame):
        t = self.n * 0.1
        self.n += 1
        out = [person(1, 130)]
        if 3 <= t <= 7.7:
            bx = 620 + (150 - 620) * min(1, (t - 3) / 3) if t < 6 else 150 + 300 * (t - 6)
            out.append(person(2, bx))
        holder_x = 130 if t < 6 else (150 + 300 * (t - 6) if t <= 7.7 else None)
        if holder_x is not None:
            out.append(TrackObs(3, (holder_x - 8, 215, holder_x + 14, 240), 0.8, "handbag", "object"))
        return out


class Empty:
    def start_video(self): pass
    def track(self, frame): return []


def upload(client, tmp_path, cfg="{}"):
    p = tmp_path / "scene.mp4"
    make_video(p)
    with p.open("rb") as f:
        return client.post("/api/videos", files={"file": ("scene.mp4", f, "video/mp4")}, data={"config": cfg})


def test_full_flow(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.PROCESS_FPS", 10)
    det.set_detector(TheftScript())
    r = upload(client, tmp_path)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "Queued" and v["stage"] == "Video uploaded" and v["stats"] is None
    assert v["duration"] == "00:00:14" and (v["width"], v["height"]) == (W, H)

    process_video(v["id"])
    a = client.get(f"/api/videos/{v['id']}/analysis").json()
    video = a["video"]
    assert video["status"] == "Completed" and video["stage"] == "Analysis completed" and video["progress"] == 1
    st = video["stats"]
    assert (st["people"], st["animals"], st["objects"]) == (2, 0, 1) and st["objectBreakdown"] == {"handbag": 1}

    # 14 s -> one full 10 s segment + a 4 s remainder
    segs = a["segments"]
    assert [(s["startSec"], s["endSec"]) for s in segs] == [(0.0, 10.0), (10.0, 14.0)]
    first = segs[0]
    assert first["classification"] == "high" and "appears to take" in first["summary"]
    assert (first["people"], first["animals"], first["objects"]) == (2, 0, 1)
    assert first["frame"] and client.get(first["frame"]).headers["content-type"] == "image/jpeg"
    assert segs[1]["classification"] == "normal" and segs[1]["people"] == 1

    # incident has everything the spec asks for
    inc = [e for e in a["events"] if e["kind"] == "transfer"]
    assert len(inc) == 1
    e = inc[0]
    assert e["severity"] == "high" and e["severityLabel"] == "High-Priority Incident" and 5.5 <= e["startSec"] <= 6.6
    assert {x["name"] for x in e["entities"]} == {"Person 1", "Person 2", "Object 1"} and e["confidence"] > 0.3
    assert e["segmentIndex"] == 0 and e["filename"] == "scene.mp4" and client.get(e["frame"]).status_code == 200

    # entities: names, appearances, thumbnails; overlay tracks
    people = [x for x in a["entities"] if x["group"] == "person"]
    assert sorted(p["name"] for p in people) == ["Person 1", "Person 2"] and all(client.get(p["thumbnail"]).status_code == 200 for p in people)
    tr = client.get(f"/api/videos/{v['id']}/tracks").json()
    assert len(tr) == 3 and all(t["obs"] and len(t["obs"][0]) == 6 for t in tr)

    # overview
    ov = client.get("/api/overview").json()
    assert (ov["videos"], ov["analysed"], ov["people"], ov["animals"], ov["objects"]) == (1, 1, 2, 0, 1)
    assert ov["incidents"] == 1 and {d["severity"] for d in ov["distribution"]} == {"normal", "unusual", "suspicious", "high"}

    # search: answers come from stored analysis and never claim more than it supports
    s = lambda q: client.get("/api/search", params={"q": q}).json()
    r1 = s("When did someone steal the handbag?")
    assert [x["title"] for x in r1["results"]] == [e["title"]] and "Earliest" in r1["answer"]
    assert "2 unique" in s("How many people appeared?")["answer"]
    assert s("Were any animals detected?")["answer"].startswith("No animals")
    assert len(s("Show all suspicious activities")["results"]) == 1
    assert "Person 1" in s("Which person stayed the longest?")["answer"]
    assert len(s("What happened between 00:00 and 00:05")["results"]) == 1
    assert s("When did someone enter the restricted area?")["results"] == []

    # report
    pdf = client.get(f"/api/videos/{v['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 5000

    # re-analysis replaces results: no duplicates, identical stats
    for _ in range(2):
        process_video(v["id"])
    again = client.get(f"/api/videos/{v['id']}/analysis").json()
    assert again["video"]["stats"] == st and len(again["events"]) == len(a["events"]) and len(again["segments"]) == 2
    assert client.get("/api/overview").json()["people"] == 2

    assert client.delete(f"/api/videos/{v['id']}").status_code == 204
    assert client.get("/api/overview").json()["videos"] == 0


def test_empty_scene_reports_zeroes_not_fake_data(client, tmp_path):
    det.set_detector(Empty())
    v = upload(client, tmp_path).json()
    process_video(v["id"])
    a = client.get(f"/api/videos/{v['id']}/analysis").json()
    assert a["video"]["stats"]["people"] == 0 and a["events"] == [] and a["entities"] == []
    assert all(s["classification"] == "normal" and "No people" in s["summary"] and s["confidence"] is None for s in a["segments"])
    assert client.get("/api/search", params={"q": "show all suspicious activities"}).json()["results"] == []


def test_optional_zone_rules_still_work(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.PROCESS_FPS", 10)
    det.set_detector(TheftScript())
    cfg = '{"restrictedZone": [[0.0,0.2],[0.3,0.2],[0.3,1.0],[0.0,1.0]]}'   # around the victim at x=130/640=0.2
    v = upload(client, tmp_path, cfg).json()
    process_video(v["id"])
    evs = client.get("/api/events", params={"kind": "restricted_entry"}).json()
    assert evs and evs[0]["severity"] == "suspicious" and evs[0]["frame"]


def test_rejects_bad_uploads_and_reports_failures(client, tmp_path):
    assert client.post("/api/videos", files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post("/api/videos", files={"file": ("a.mp4", b"not a video", "video/mp4")}).status_code == 422
    assert upload(client, tmp_path, '{"restrictedZone": [[0,0],[1,1]]}').status_code == 422

    class Boom:
        def start_video(self): pass
        def track(self, f): raise RuntimeError("model exploded")
    det.set_detector(Boom())
    v = upload(client, tmp_path).json()
    process_video(v["id"])
    got = client.get(f"/api/videos/{v['id']}").json()
    assert got["status"] == "Failed" and "model exploded" in got["error"]
