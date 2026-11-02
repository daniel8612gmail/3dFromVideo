# Multi-photo v1 API (system sessions)

This API is additive. The existing single-photo endpoints (`upload.php`,
`status.php`, `get-glb.php`, and cleanup) are unchanged and continue to use
their existing top-level 32-character session directories and `model.glb`.

`systemSessionId` identifies a logical scan containing multiple images,
capture metadata, and versioned aggregate models. It is independent of
`arSessionEpochId` and is carried separately in the API URL/body, not in frame
metadata. Frames in one logical scan may come from different AR session epochs
and use different `referenceFrameId` values, provided every explicit
`cameraToFirstFrame` pose is already expressed in the same common scan frame.
An Android `deviceId` is currently a client-declared identifier used only for
a local filesystem lease: there is no Android authentication in this project,
so `deviceId` is not proof of identity or authorization.

## Endpoints

All JSON responses use UTF-8. Errors have the form
`{"success":false,"error":"..."}`. IDs are generated as 32 lowercase hex
characters; frame IDs must match `[A-Za-z0-9_-]{1,96}`.

### Create or resume the active device session

`POST /api/v1/sessions.php`

```json
{"deviceId":"android-installation-local-id"}
```

Returns `201` with a new `systemSessionId`, or `200` with the already-active
session for that declared device ID (`reused: true`). A device lease is
serialized with `flock` and an atomic JSON write. Different device IDs may
create and process sessions concurrently. Completing a session releases its
lease.

### Read status and frame progress

`GET /api/v1/sessions.php?systemSessionId=<id>`

Returns system status, latest published `currentVersion`, and each frame's
`frameId`, `sequence`, `status`, `progress`, and optional processing error.
Possible frame states include `queued`, `processing`, `aggregator_pending`,
`aggregating`, `complete`, and `failed`. Session statuses include `collecting`,
`queued`, `processing`, `closing`, `ready`, `complete`, and `error`.

Progress/status is stored in shared files; there is no separate API service or
database.

### Upload an image and metadata

`POST /api/v1/frames.php?systemSessionId=<id>` as `multipart/form-data`:

* `photo`: one JPEG, PNG, or WebP image, 1 byte–20 MiB.
* `metadata`: a JSON object, described below.

Returns `202` for a new queued frame. A byte-for-byte identical upload with
the same canonical metadata and the same `frameId` is idempotent and returns
the frame's current status (`200`). Reusing a `frameId` with a different
content hash or metadata returns `409`. A duplicate sequence, unstable camera
profile, or closed session also returns `409`.
The session is capped at 500 frames.

Required `metadata` fields:

```json
{
  "frameId": "frame_0001",
  "sequence": 0,
  "timestampMs": 1780000000123,
  "trackingState": "TRACKING",
  "assetId": "asset-id",
  "sha256": "<64 lowercase hexadecimal characters>",
  "mimeType": "image/jpeg",
  "width": 1920,
  "height": 1080,
  "orientation": 0,
  "imageTransform": {
    "sourceWidth": 1920,
    "sourceHeight": 1080,
    "rotationDegrees": 0,
    "mirrorX": false,
    "crop": {"x": 0, "y": 0, "width": 1, "height": 1}
  },
  "arSessionEpochId": "arcore-epoch-id",
  "referenceFrameId": "anchor-or-reference-id",
  "cameraToFirstFrame": {
    "translationM": [0, 0, 0],
    "rotationQuaternionXyzw": [0, 0, 0, 1]
  },
  "intrinsics": {"fx": 1200, "fy": 1200, "cx": 960, "cy": 540},
  "distortionStatus": "not_provided",
  "cameraProfile": {
    "cameraId": "stable-camera-profile",
    "imageWidth": 1920,
    "imageHeight": 1080
  }
}
```

The API retains the complete submitted capture metadata object, including
additional capture-specific fields, and includes it in idempotency checks.
`systemSessionId` is not a frame metadata field. The model-convention fields
`mogeToCameraMatrix4x4`, `scaleEstimate`, and `axes` are reserved and rejected
if supplied by a client.

### Capture-client migration note

The Android implementation is intentionally out of scope for this backend
change. A client migrating its multi-frame upload must replace
`cameraToSystemSessionFrame` with
`cameraToFirstFrame: {translationM, rotationQuaternionXyzw}` and compute the
pose in the logical scan frame before upload. `systemSessionId` is the scan
identity, not an ARCore epoch; clients may keep AR epoch/reference IDs as
capture diagnostics, but the backend does not derive or transform poses from
them. The first submitted frame is sequence 0 with identity pose. Existing
legacy single-image uploads and their `model.glb` flow are unchanged.

Validation rules:

* `sequence` is a non-negative integer and unique within the system session.
  The first uploaded frame must have `sequence: 0`;
  sequence `0` is the scan origin and must have identity
  `cameraToFirstFrame` (`translationM: [0, 0, 0]` and identity quaternion
  `[0, 0, 0, ±1]`); `timestampMs` and image dimensions are positive integers.
* Image MIME and exact width/height are read from the uploaded bytes; the
  claimed MIME/dimensions must match. SHA-256 is calculated and compared with
  the supplied hash. The server does not decode/re-encode or change the image
  bytes.
* `orientation` and `imageTransform.rotationDegrees` are multiples of 90.
  `imageTransform` declares how the source AR image maps to the uploaded image:
  normalized source crop, clockwise rotation, horizontal mirroring, source
  dimensions, and resulting uploaded dimensions (`width`/`height`). It is
  descriptive metadata; the API does not silently apply the transform.
  Upload/storage accepts valid descriptive transforms unchanged, but frame
  aggregation currently admits only the no-op values: `orientation: 0`,
  source dimensions equal to uploaded dimensions, `rotationDegrees: 0`,
  `mirrorX: false`, and the full-frame crop `{x: 0, y: 0, width: 1,
  height: 1}`. Missing, unknown, rotated, mirrored, or cropped transform
  metadata fails aggregation explicitly; no identity transform is inferred.
* `trackingState` is `TRACKING`, `PAUSED`, `STOPPED`, or `LIMITED`.
  `arSessionEpochId` and `referenceFrameId` identify capture/tracking context;
  neither is `systemSessionId`, and they may differ between frames in one
  logical scan.
* Every frame must explicitly provide
  `cameraToFirstFrame.translationM` in metres and a normalized
  `cameraToFirstFrame.rotationQuaternionXyzw` xyzw quaternion, already
  expressed in the common logical scan frame. The quaternion is the camera's
  full 3D orientation (including heading, pitch, and roll) relative to the
  first frame, not just its forward/look direction. Translation-only input is
  insufficient: the aggregator applies both translation and rotation to every
  vertex before merging geometry and textures. For a camera pose reported by
  ARCore in the same tracking epoch, the relative transform can be computed as
  `inverse(T_world_from_first_camera) * T_world_from_current_camera`; convert
  the result to the API's documented coordinate convention. When tracking
  epochs differ, the client must first register them into the same scan frame.
  The service does not infer a scan pose from `arSessionEpochId` or
  `referenceFrameId`, and clients must not use or fall back to
  `cameraToSystemSessionFrame`. `intrinsics` are image-specific `fx`, `fy`,
  `cx`, and `cy` in uploaded-image pixels. Camera pose, intrinsics, image
  transforms, `arSessionEpochId`, and all other capture metadata are retained
  as submitted.

  The aggregator converts the normalized xyzw quaternion to a 3D rotation
  matrix and composes it with the frame translation and the trusted MoGe/GLB
  coordinate-basis transforms. Consequently, rotating a handheld camera while
  keeping its position fixed still rotates that frame's reconstructed geometry
  around the scan origin according to the supplied pose.
* This version accepts only `distortionStatus: "not_provided"`. This means
  distortion is unknown/not supplied; it **does not** mean distortion is zero.
* `cameraProfile` is an opaque non-empty JSON object that must remain
  structurally identical for all frames in a system session.
* Clients do not provide model axes, MoGe transforms, or scale. The canonical
  metric-v3 MoGe convention is accepted only from the trusted convention
  sidecar produced after successful worker processing and validated against
  the corresponding GLB and captured image bytes. A missing, stale,
  malformed, unsupported, or unverified sidecar fails aggregation closed: no
  new model version is published and the prior published version remains
  available.
* For `system_frame` jobs, runtime provenance is trusted only when both the Python worker (which receives
  `--require-provenance` explicitly for these jobs) and the
  Node/aggregator process are configured with
  `MOGE_EXPECTED_CODE_REVISION=74fbce054ebed49800de42d0ad0e83495065719a`
  and the same approved value for `MOGE_EXPECTED_CHECKPOINT_SHA256`. The
  actual source revision and checkpoint SHA-256 must verify against those
  pins. The Python worker does not require these pins for legacy image→GLB
  jobs. If either value is missing or does not match during a system-frame
  job, sidecar validation fails and aggregation does not publish a model.

### Complete/close frame intake

`POST /api/v1/complete.php`

```json
{"systemSessionId":"0123456789abcdef0123456789abcdef"}
```

This is idempotent, closes intake immediately, and releases the device lease.
Already queued frames continue processing and session status becomes
`complete` when they finish. No more frames may be uploaded to a closed
session.

### Download an immutable GLB version

`GET /api/v1/model.php?systemSessionId=<id>&version=<positive-version>`

Returns `model/gltf-binary` with immutable cache headers. The version must
exist; this endpoint never substitutes `model.glb` or a newer version.
Status gives the latest committed version. Versioned files live at
`data/system-sessions/<systemSessionId>/model.vN.glb`.

## Storage, queue, and worker protocol

The PHP API writes to
`system/web_img3d/data/system-sessions/<systemSessionId>/`. Configure the
WebSocket worker's `DATA_DIR` to the same shared storage root as PHP (for
example, the deployed shared `data/` directory). The Node legacy scanner
accepts only top-level 32-hex legacy directories; the nested
`system-sessions/` root is explicitly excluded from the one-photo flow.

Each frame has its own `frames/<frameId>/` directory and JSON state. The Node worker pool fairly dispatches queued frames across logical sessions
up to available worker capacity. There is no same-session dispatch gate: more
than one frame in a scan can be processed concurrently by idle workers.
Worker disconnects/errors retry a frame up to three attempts; a completed
frame is not sent again. The worker pool only runs the existing image-to-GLB
pipeline and durably stages its verified frame GLB in a broker outbox. A
separately supervised authenticated aggregator agent consumes/replays that
outbox. Per-frame progress remains available from the PHP status endpoint. A
terminal frame/aggregation failure marks the session
`error` and blocks later queued frames so the published version cannot
silently omit a failed earlier capture; continue in a new system session.

Legacy jobs retain `type: "job"` with `sessionId` and `ready_for_glb`.
Multi-photo jobs use the same authenticated WebSocket and image-processing
pipeline, but are explicitly tagged:

```json
{
  "type": "job",
  "jobType": "system_frame",
  "jobId": "...",
  "systemSessionId": "...",
  "frameId": "...",
  "filename": "frame_0001.jpg",
  "size": 12345,
  "sha256": "..."
}
```

The agent reports progress with the same `jobType`, `systemSessionId`, and
`frameId`. For a successful system-frame run, Python writes
`frame/frame_planes.glb` and its adjacent
`frame/frame_planes.glb.convention.json`. The worker reads the bounded
sidecar and sends it in the authenticated `ready_for_frame_glb` JSON message
as `conventionSidecar`, then sends the GLB binary:

```json
{
  "type": "ready_for_frame_glb",
  "jobType": "system_frame",
  "jobId": "...",
  "systemSessionId": "...",
  "frameId": "...",
  "conventionSidecar": {"schemaVersion": 1}
}
```

The actual `conventionSidecar` value contains the complete sidecar document.
The server routes the binary only to the matching active worker job. Legacy
message names remain unchanged. Once the broker has durably saved the frame
GLB and request metadata, it sends the worker `job_complete` with status
`aggregator_pending`; this only releases the image worker and does not claim
that a model has been published.

Node validates the sidecar before accepting it: `schemaVersion` must be `1`;
the convention, bases, and matrices must match the fixed canonical values;
scale must be exactly `1.0 m/unit`; the official code revision and checkpoint
must match the configured provenance pins; and the canonical orientation
proof must be valid. Node also verifies the sidecar's GLB SHA-256 against the
received binary and its image SHA-256 against the bytes captured for that
frame. The validated sidecar is stored adjacent to the received GLB, and the
aggregation manifest references it with `conventionSidecarPath`.

Missing, malformed, unsupported, stale, or mismatched convention metadata
fails the frame/aggregation closed. There is no client-provided transform,
scale, or axes, no identity-convention fallback, and no SfM fallback. A
failed frame does not replace or deactivate the already published model.

The broker stores `outbox/<requestId>/input.glb`, `metadata.json`, and
`state.json` under each session directory using atomic, fsynced file writes.
`requestId` is stable across replays. On aggregator authentication/reconnect,
the broker replays unfinished requests; both peers bind the request ID,
session/frame IDs, size, GLB SHA-256, canonical metadata SHA-256, and binary
payload. The aggregator agent durably stages the received input under
`aggregator-inbox/<requestId>/` before returning `durable-accepted`. It then
invokes the separately deployed publisher CLI and sends `committed` only after
the publisher confirms publication. Terminal `rejected` acknowledgements
fail that frame; reconnecting or retrying a request with the same ID must be
idempotent. The broker never starts `geom_aggregate_glb.py`, creates model
versions, or writes `current-version.json`.

The repository publisher CLI is `system/py/geom_publish_glb.py`. Configure
`PUBLISHER_CLI` as the Python interpreter and `PUBLISHER_SCRIPT` as the absolute
path to that script; the aggregator agent launches the interpreter directly
(without a shell) and passes the script path before these arguments:

```text
--request-id <stable-id>
--system-session-id <logical-scan-id>
--frame-id <frame-id>
--input-glb <durably-staged-input.glb>
--metadata-json <publisher-metadata.json>
--data-dir <shared-DATA_DIR>
--result-json <publisher-result.json>
```

`metadata-json` is schema 1 and includes the stable request/session/frame IDs,
the current frame sequence and input SHA-256, plus the ordered completed-frame
entries (frame ID, sequence, shared `DATA_DIR` GLB and convention-sidecar
relative paths, and explicit `cameraToFirstFrame` containing
`translationM` and `rotationQuaternionXyzw` in xyzw order).
All worker-complete frames present in the broker's durable snapshot (including
previously committed frames) are included with the newly staged frame. The
agent rewrites the current entry's GLB path to its staged input and copies the
broker-validated adjacent convention sidecar beside that staged GLB, updating
the current entry's sidecar path accordingly.
Paths are relative to `DATA_DIR`; the CLI must reject any path escaping that
root. The CLI must take a per-session lock, be idempotent on `requestId`,
allocate versions while holding that lock, write immutable
`model.vN.glb` files, atomically advance the existing
`current-version.json` pointer, and only then write the result JSON:

```json
{"requestId":"<stable-id>","status":"committed","version":1}
```

A deterministic permanent input/contract failure may instead return
`{"requestId":"<stable-id>","status":"rejected","error":"..."}` with exit code
zero. Missing/malformed result files and nonzero exits are treated as
transient: the supervised agent retries without reporting success. The
repository publisher CLI implements this contract directly, so no wrapper is
needed when using that script. The image worker's Python stage timeout/output
handling and legacy image→GLB invocation remain unchanged.

The current `system/py/geom_aggregate_glb.py` is **not** this publisher CLI. It
accepts `--manifest <json> --output <glb>`; its manifest requires
`schemaVersion`, `systemSessionId`, `targetVersion`, and frames with flattened
`translationM`/`rotationQuaternionXyzw`. A publisher adapter must translate the
stable metadata into that manifest, select `targetVersion` under its
per-session lock, resolve all relative inputs against `DATA_DIR` (the Python
script resolves relative manifest paths against the manifest directory), and
provide an adjacent `*.glb.convention.json` for each GLB. The aggregator agent
stages the current input sidecar adjacent to its staged GLB and updates the
publisher metadata path accordingly. `geom_publish_glb.py` performs this
adapter/publisher work, including locking, version allocation, idempotent
request handling, immutable version publication, and the current-version
pointer update. It invokes the geometry aggregation implementation rather
than asking Node to perform geometry or inference.
The worker agent uses `PYTHON` (Windows defaults to `python`) and bounds each
Python stage to 256 KiB of forwarded output with a configurable
`PYTHON_STEP_TIMEOUT_MS` (default 45 minutes); worker shutdown terminates its
active child process.

The publisher consumes only the validated metric-v3 convention from the
worker sidecar and applies the documented canonical transform; it must not
infer convention, model scale, or axes from client metadata. Existing
published models are never overwritten. The publisher, not the broker or
aggregator transport agent, owns per-session locking and atomic version/pointer
publication.

For `system_frame`, the worker must produce the convention sidecar only after
successful processing; it passes `--require-provenance` to both
`ai_moge3.py` and `geom_process.py`. A readable frame GLB without its
matching, verified sidecar is not sufficient input for aggregation. Legacy
image→GLB jobs do not receive that flag and retain the prior MoGe runtime
requirements (`MOGE_MODEL_PATH` and a working MoGe installation); they may
produce a GLB without a convention sidecar. For multi-photo deployment, configure
`MOGE_EXPECTED_CODE_REVISION=74fbce054ebed49800de42d0ad0e83495065719a` and
the same approved `MOGE_EXPECTED_CHECKPOINT_SHA256` on the Python worker and
Node broker; the publisher runtime must also pass those pins through when it
invokes the current Python aggregator. Verify runtime provenance against both
pins. This
does not relax provenance or convention validation for aggregation.

### Coplanar geometry and texture fusion

The Python aggregator combines textured, UV-mapped rectangular patches only
when their fitted planes agree within 1 degree and 5 mm plus 0.1% of the
smaller patch diagonal, and their projected footprints overlap by at least
20% of the smaller footprint. Distant, weakly-overlapping, materially
non-coplanar, and non-rectangular patches are not treated as duplicates;
touching-but-not-overlapping surfaces remain separate. A missing texture
keeps that mesh separate, while a present but unreadable image or invalid UV
data fails aggregation explicitly. Distinct real surfaces that are exactly
co-located, coplanar, rectangular, and substantially overlapping cannot be
distinguished from duplicate captures using the present GLB/UV data alone;
the sequence-based compositing rule is deterministic for that ambiguous case.

Merged patches become one GLB mesh with one orthographic texture atlas. The
atlas is built by projecting each input triangle through its existing UVs into
the registered session plane; triangle UVs are rewritten to address that
atlas. Thus uncovered areas still use their source image and a later frame
does not erase content outside its own footprint. Where opaque or translucent
pixels overlap, source patches are composited in ascending `(sequence,
frameId, node)` order: later sources alpha-over earlier ones, deterministically.
There is no image-quality score in the current producer contract, so sequence
is the explicit tie-breaker. The fused mesh retains the source triangles and
footprint, projecting accepted registration noise onto the shared plane
(coincident duplicate triangles may be collapsed when identical); the
aggregator does not fill the bounding rectangle or bridge gaps. Atlas
dimensions preserve the highest available per-axis texel density subject to
an 8192-pixel side and 32-million-pixel allocation ceiling.

`merged_patch_sources` and `texture_merge_policy` GLB extras preserve source
frame, sequence, GLB, node, and compositing diagnostics. Texture fusion
requires each candidate GLB to contain a readable base-color image and finite
per-vertex UVs; invalid texture data is an aggregation error rather than a
fallback to a seemingly successful geometry-only merge. Meshes that do not
meet the strict merge criteria remain separate with their original material.

`npm start` runs the source entrypoint `src/server.js`. `npm run build` emits
the bundled `system/img3d_ws/server.js` expected by the existing systemd
deployment/install contract. Do not edit the ignored bundle directly.

## Compatibility and operational limitations

* No changes are made to the existing single-photo PHP endpoints or UI.
* There is no frame-registration operation yet. The capture client must
  compute `cameraToFirstFrame` in a common logical scan frame; the API does not
  infer transforms between AR epochs/references.
* The declared `deviceId` lease is local coordination only, not Android
  authentication. Anyone able to call the PHP endpoints and guess/obtain a
  session ID can access that session; deploy behind the same access controls
  used for the current API.
* PHP API validation requires PHP 8.1+ (`array_is_list`) and an upload limit
  configured to allow 20 MiB files (`upload_max_filesize` and
  `post_max_size`).
* Focused checks: `php -n system/web_img3d/tests/test_system_session_contract.php`
  and, from `system/img3d_ws/`, `npm run test:system`.

## Aggregator agent deployment

The broker and aggregator agent connect through the existing authenticated
WebSocket URL. The aggregator has a separate credential and role; it is not an
image worker and is never eligible for image dispatch.

1. Register a distinct, randomly generated token in the Node broker's
   `agents.json` (protect this file as a secret):

   ```json
   {
     "agents": {
       "worker-01": {"token": "<worker-secret>", "role": "worker"},
       "img3d-aggregator-01": {"token": "<different-aggregator-secret>", "role": "aggregator"}
     }
   }
   ```

   Older worker entries without `role` are treated as `worker`. The server
   derives the role from this trusted file and checks the requested role on
   aggregator authentication. Never reuse a worker token.
   Reload the existing broker process after editing the credentials, for
   example with `sudo systemctl kill -s HUP img3d-ws.service`.

2. Deploy `system/img3d_ws_aggregator/` on the publisher host, install its
   Node dependencies with `npm ci`, and create a root-owned mode-0600
   environment file based on `.env.example`. Set `WS_URL` to the same public
   `/ws` endpoint used by workers, `AGGREGATOR_ID`/`AGGREGATOR_TOKEN` to the
   registered credential, and `DATA_DIR` to the exact shared storage root.
   The service user needs read access to session frames and write access to
   `system-sessions/*/aggregator-inbox/`; the publisher CLI needs permission
   to write versioned models and `current-version.json`. Ensure Python 3.10+
   and the publisher's Python dependencies are installed for the configured
   interpreter.

3. Configure `PUBLISHER_CLI` and `PUBLISHER_SCRIPT` for the deployed checkout.
   The `.env.example` defaults assume `/usr/bin/python3` and a checkout at
   `/opt/3dFromVideo`; update either absolute path when deployment differs.
   `system/py/geom_publish_glb.py` is the publisher entrypoint. Do not point
   the command at the lower-level `geom_aggregate_glb.py` script, which has a
   different manifest/output interface.

4. Install
   `system/img3d_ws_aggregator/img3d-ws-aggregator.service` as
   `/etc/systemd/system/img3d-ws-aggregator.service`, adjust its user and
   installation paths, then run:

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now img3d-ws-aggregator.service
   sudo journalctl -u img3d-ws-aggregator.service -f
   ```

5. Keep the existing broker service enabled. Its WebSocket payload limit
   defaults to 600 MiB for validated frame-GLB transport and can be set with
   `MAX_WS_PAYLOAD_BYTES` (maximum 1 GiB). Ensure the reverse proxy permits
   WebSocket connections and long-lived idle connections. The agent reconnects
   with exponential backoff; pending outbox requests replay after reconnect
   and after either service restarts.

The shared filesystem is the cross-process data plane. `requestId` and
canonical metadata/input hashes make transport replay idempotent. The
publisher must independently enforce path containment, per-session locking,
idempotency, immutable version files, and atomic pointer updates; transport
acknowledgements do not replace those publication guarantees.
