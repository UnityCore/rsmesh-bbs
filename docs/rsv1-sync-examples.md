# rsv1 sync message examples

Release 1.1

Examples of every **rsv1** peer sync message on the mesh wire. These samples were generated from the encode functions in `rsmesh_bbs/sync_wire.py`. On the wire, JSON is compact (no spaces); pretty JSON is shown below for readability.

See also [Sync wire formats](../README.md#sync-wire-formats) in the main README and the [admin tool sync protocol table](README-ADMIN.md#sync-protocols).

## Envelope

Every rsv1 message uses:

```
RS|1|<TYPE>|<json-payload>
```

| Part | Meaning |
|------|---------|
| `RS` | Wire prefix |
| `1` | Wire version (`rsv1` → `RS|1|…`) |
| `<TYPE>` | Message type (uppercase) |
| `<json-payload>` | Compact JSON object |

---

## BULLETIN

**Keys:** `b` board, `sn` sender short name, `sub` subject, `body` content, `uid` unique ID, `pin` pinned (`Y`/`N`)

**Unpinned (create or update):**

```
RS|1|BULLETIN|{"b":"General","sn":"OPS","sub":"Trail conditions","body":"Muddy north of mile 3.","uid":"550e8400-e29b-41d4-a716-446655440001","pin":"N"}
```

```json
{
  "b": "General",
  "sn": "OPS",
  "sub": "Trail conditions",
  "body": "Muddy north of mile 3.",
  "uid": "550e8400-e29b-41d4-a716-446655440001",
  "pin": "N"
}
```

**Pinned urgent bulletin:**

```
RS|1|BULLETIN|{"b":"Urgent","sn":"OPS","sub":"Evacuation notice","body":"Leave sector 4 immediately.","uid":"550e8400-e29b-41d4-a716-446655440001","pin":"Y"}
```

**Notes:** Upsert by `uid` on ingest. Missing `pin` decodes as `N`. Re-sending with the same `uid` updates board, subject, body, and pin on rsv1 peers.

---

## MAIL

**Keys:** `s` sender hex ID, `ssn` sender short name, `r` recipient hex ID, `rsn` recipient short name, `sub`, `body`, `uid`

**Hex recipient:**

```
RS|1|MAIL|{"s":"!a1b2c3d4","ssn":"ALICE","r":"!e5f6a7b8","rsn":"BOB","sub":"Meet at base","body":"Radio check at 1800.","uid":"550e8400-e29b-41d4-a716-446655440002"}
```

```json
{
  "s": "!a1b2c3d4",
  "ssn": "ALICE",
  "r": "!e5f6a7b8",
  "rsn": "BOB",
  "sub": "Meet at base",
  "body": "Radio check at 1800.",
  "uid": "550e8400-e29b-41d4-a716-446655440002"
}
```

**Short-name recipient** (`r` empty, `rsn` used):

```
RS|1|MAIL|{"s":"!a1b2c3d4","ssn":"ALICE","r":"","rsn":"BOB","sub":"Ping","body":"Are you up?","uid":"550e8400-e29b-41d4-a716-446655440002"}
```

**Notes:** Insert-only by `uid` (duplicate ingests skipped).

---

## CHANNEL

**Keys:** `n` name, `psk` PSK, `uid` unique ID

```
RS|1|CHANNEL|{"n":"mesh-chat","psk":"AQ==","uid":"550e8400-e29b-41d4-a716-446655440003"}
```

```json
{
  "n": "mesh-chat",
  "psk": "AQ==",
  "uid": "550e8400-e29b-41d4-a716-446655440003"
}
```

**Notes:** `uid` is required for rsv1. Ingested channels are unpublished locally.

---

## DELETE_BULLETIN

**Keys:** `uid` bulletin unique ID

```
RS|1|DELETE_BULLETIN|{"uid":"550e8400-e29b-41d4-a716-446655440001"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440001" }
```

**Notes:** On rsv1 peers, deletes by `uid` directly (no tc2-style reconcile workflow).

---

## DELETE_MAIL

**Keys:** `uid` mail unique ID

```
RS|1|DELETE_MAIL|{"uid":"550e8400-e29b-41d4-a716-446655440002"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440002" }
```

---

## DELETE_CHANNEL

**Keys:** `uid` channel unique ID

```
RS|1|DELETE_CHANNEL|{"uid":"550e8400-e29b-41d4-a716-446655440003"}
```

```json
{ "uid": "550e8400-e29b-41d4-a716-446655440003" }
```

**Notes:** rsv1-only; triggers reconcile workflow on the receiving peer.

---

## NODE

**Keys:** `id` node hex ID, `sn` short name, `ln` long name, `lh` last heard (Unix epoch string)

```
RS|1|NODE|{"id":"!a1b2c3d4","sn":"ALICE","ln":"Alice Node","lh":"1700000000"}
```

```json
{
  "id": "!a1b2c3d4",
  "sn": "ALICE",
  "ln": "Alice Node",
  "lh": "1700000000"
}
```

**Notes:** rsv1-only. Used when **Sync mesh nodes** is enabled on the peer.

---

## CHUNK (transport wrapper)

When a complete `RS|1|…` message exceeds **200 bytes**, it is split into one or more `CHUNK` packets. Each chunk carries a fragment of the **inner** message string.

**Keys:** `u` transfer UUID, `i` chunk index (0-based), `n` total chunks, `p` payload fragment

**Example (chunk 0 of 4 for an oversized BULLETIN):**

```
RS|1|CHUNK|{"u":"95f49967-6bc2-4e9c-b970-0eb671154b02","i":0,"n":4,"p":"RS|1|BULLETIN|{\"b\":\"General\",\"sn\":\"OPS\",\"sub\":\"Large post\",\"body\":\"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
```

```json
{
  "u": "95f49967-6bc2-4e9c-b970-0eb671154b02",
  "i": 0,
  "n": 4,
  "p": "RS|1|BULLETIN|{\"b\":\"General\",\"sn\":\"OPS\",\"sub\":\"Large post\",\"body\":\"xxxxxxxx..."
}
```

**Notes:** Reassembly concatenates all `p` fragments in order (`i` 0 … `n-1`) to rebuild the inner message, which is then parsed as a normal `RS|1|TYPE|…` envelope. Partial sequences expire after 300 seconds.

---

## Quick reference

| Type | JSON keys | rsv1-only? |
|------|-----------|------------|
| `BULLETIN` | `b`, `sn`, `sub`, `body`, `uid`, `pin` | No (tc2 uses pipe format) |
| `MAIL` | `s`, `ssn`, `r`, `rsn`, `sub`, `body`, `uid` | No |
| `CHANNEL` | `n`, `psk`, `uid` | No (`uid` required on rsv1) |
| `DELETE_BULLETIN` | `uid` | No |
| `DELETE_MAIL` | `uid` | No |
| `DELETE_CHANNEL` | `uid` | Yes |
| `NODE` | `id`, `sn`, `ln`, `lh` | Yes |
| `CHUNK` | `u`, `i`, `n`, `p` | Yes (transport) |
