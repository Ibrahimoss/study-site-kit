# Social API (likes, comments, shares, watch stats)

With `features.social: true` in course.json, the shorts feed talks to an API on the same host as the site. The kit does not ship this server: this file is the contract a server has to meet. Everything else on the page works without it.

## Where the page looks

- `site.api` (default `/api/`): the base path of every request below, from the site's origin. `GET /api/health` with the default.
- `site.shareBase` (default `/s/`): the share pages, from the site's origin. `GET /s/<id>`.

One server can serve several sites on the same host (for example one at `/` and one at `/biology/`) as long as short ids do not repeat across the sites: a short id alone tells the server which site it belongs to.

## How the page uses it

1. When the shorts feed first opens, the page calls `GET <api>health` with a 2.5 second timeout. Only an HTTP 200 with `{"ok": true}` counts as "the API answers".
2. If it answers, the page loads `GET <api>social`, then polls it every 20 seconds while the feed is open. Likes, shares and comments go to the API.
3. If it does not answer, the page sends nothing more for this visit: likes and comments are kept in this browser only (and say so in the comment sheet), share links point at `<site.url>#short.<id>`, and no watch stats are sent.

With social off, none of this runs and the page makes no request to any API.

## Visitors and headers

Visitors are anonymous. The page keeps a random id in local storage (`<slug>-anon-id`, 8 to 64 characters of `A-Za-z0-9-`, usually a UUID) and sends it on every call as `X-Client-Id`. The server should store no names, accounts or addresses, and should never show one visitor's id to another.

`X-Admin-Token` is sent when local storage holds `<slug>-admin` (set by hand by the site owner). A server that accepts it lets that visitor delete any comment.

Every request and response body is JSON (`Content-Type: application/json`). Error responses may carry `{"ok": false, "reason": "..."}`: the page shows `reason` to the visitor, so it should be short and plain.

## Endpoints

### `GET <api>health`

```json
{ "ok": true }
```

### `GET <api>social`

Headers: `X-Client-Id` (optional; without it `myLikes` is empty and `me` is null).

```json
{
  "likes":    { "<short id>": 12 },
  "shares":   { "<short id>": 3 },
  "myLikes":  [ "<short id>" ],
  "comments": { "<short id>": [ { "id": "9f2c41d0a7b3e815", "text": "Nice one", "at": 1767000000000, "mine": false, "name": "Quiet Otter:443" } ] },
  "admin":    false,
  "me":       "Quiet Otter:443"
}
```

- Counts are totals over all visitors. A short with no likes or shares can be left out.
- `comments`: newest first, per short; the server may cap the number per short. `at` is milliseconds since 1970 (UTC). `mine` is true for the asking visitor's own comments (the page offers Delete on them).
- `name` and `me`: the visitor's handle, a stable pseudonym the server makes from the visitor id (never the id itself). A handle may end in a code-like tag that the page shows in the code font: `:<1 to 5 digits>` (such as `Quiet Otter:443`) or `<<<...>>>`. Without `name` the page shows "Anonymous".
- `admin`: true when `X-Admin-Token` is valid.

### `POST <api>like`

Headers: `X-Client-Id` (required). Body:

```json
{ "short": "<short id>", "on": true }
```

`on: true` likes, `on: false` takes the like back. Liking twice counts once. Answer `{"ok": true}`, or a 4xx with `{"ok": false, "reason": "..."}` (for example an unknown short or too many requests); the page then undoes the heart and shows the reason.

### `POST <api>share`

Headers: `X-Client-Id` (required). Body: `{ "short": "<short id>" }`. Counts one share. Answer `{"ok": true}`. The page sends it after the visitor shared or copied the link; it ignores the answer.

### `POST <api>comments`

Headers: `X-Client-Id` (required). Body:

```json
{ "short": "<short id>", "text": "Up to 300 characters" }
```

The page trims the text, joins runs of white space into one space, and refuses empty text or more than 300 characters before sending. The server must check every comment before storing it (links, personal details, abuse) and refuse anything it cannot check.

- Posted: `{"ok": true, "comment": {"id": "...", "text": "...", "at": 1767000000000, "name": "<handle>"}}`
- Refused: `{"ok": false, "reason": "Not posted: ..."}` (HTTP 200 or 4xx); the page shows `reason` under the comment box.

### `DELETE <api>comments/<comment id>`

Headers: `X-Client-Id` (required), `X-Admin-Token` (optional). Deletes the comment if it belongs to this visitor, or any comment with a valid admin token. Answer `{"ok": true}`.

### `POST <api>views`

Anonymous watch stats, sent in batches of up to 20 with `navigator.sendBeacon` (no headers beyond the content type, so no `X-Client-Id`), or with `fetch` and `keepalive` when a beacon is not possible. Body:

```json
{ "views": [ { "short": "<short id>", "pct": 100, "secs": 24.5 } ] }
```

- One item per time a short was on screen: `pct` is how far it got (0 to 100; 100 when it played to the end), `secs` the seconds actually played.
- Sent every 30 seconds, after 10 views, and when the page is hidden or closed.
- The server should keep only totals (for example per short per day) and ignore unknown shorts. The page ignores the answer.

### `POST <api>visit`

Anonymous page views for the site's owner, one `navigator.sendBeacon` per page change, only after `<api>health` answered. Body:

```json
{ "page": "unit:t4-2:learn", "start": true, "back": false, "phone": true }
```

- `page` is the view (`home`, `shorts`, `exam`, `quick`, `plan`, ...) or `unit:<unit id>:<tab>`, lower case, at most 60 characters of `a-z 0-9 . _ : -`.
- `start`, `back` and `phone` come only with the first page of a visit (a browser tab session): whether this browser has been on the site before (a flag kept on the device, not an id) and whether the screen is phone-sized.
- The server should tell sites apart by the page's address (`Referer`), keep only daily totals (views per site and page; visits, returning visits and phone visits per site) and show them only to the admin. The page ignores the answer.

### `GET <shareBase><id>`

Not called by the page itself: it is the link the Share button gives out while the API answers (`<origin><shareBase><id>`). It should answer an HTML page with a preview card for chat apps (`og:title`, `og:description`, `og:image` from the short's poster, `og:video` from its video, both as absolute URLs under the site that owns the short), then send the visitor to the short on that site: `<site path>/#short.<id>` (for example `/#short.<id>` for a site at the root, `/biology/#short.<id>` for one at `/biology/`). Unknown ids answer 404.

The short's title, caption, poster and video are in that site's `shorts/manifest.json`.

## What the page keeps on the device

- `<slug>-shorts`: shorts watched and liked on this device (used for the feed order and the Liked view, with or without the API).
- `<slug>-anon-id`, `<slug>-admin`: see above.
- `<slug>-been` (a "came before" flag) and, for the tab session, `<slug>-visit`: used only for the visit counts.
- When the API does not answer, likes, shares and comments go into the page's own progress store, on this device only.
