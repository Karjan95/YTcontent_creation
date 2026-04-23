# Changelog: Image History Visibility & Download All Fix

**Date:** 2026-03-01
**Scope:** `ui/index.html`

---

## Problems

### 1. Generated images not visible after regeneration
When a user generated an image, then regenerated the same scene, the previous version was not visibly accessible. The "Previous versions" history strip existed in the DOM but rendered **collapsed** (`display: none`) by default. Users had to discover and click a small, low-contrast header to expand it — most didn't realize it was there.

### 2. "Download All Assets" button not working
The button silently failed to trigger file downloads due to two bugs:
- The `<a>` element used to trigger the browser download was **never appended to the DOM** before calling `.click()`. Some browsers (notably Safari) require the element to be in the document for the click to initiate a download.
- No visual feedback was provided — the button appeared to do nothing on click, with no progress indicator or completion message.

---

## Changes

### 1. Image History Strip — Auto-Expand (`ui/index.html` ~line 5018)

**Before:**
```html
<div class="history-strip-body" id="history-body-${idx}" style="display: none;">
```
```html
<span class="history-strip-toggle" id="history-toggle-${idx}">▼</span>
```

**After:**
```html
<div class="history-strip-body" id="history-body-${idx}" style="display: flex;">
```
```html
<span class="history-strip-toggle" id="history-toggle-${idx}" style="transform: rotate(180deg)">▼</span>
```

- History strip now renders **expanded by default** so previous versions are immediately visible
- Toggle arrow starts rotated (pointing up) to indicate the panel is open
- Users can still click the header to collapse/expand as before

### 2. Download All — DOM Append Fix (`ui/index.html` ~line 5362)

**Before:**
```javascript
const a = document.createElement('a');
a.href = blobUrl;
a.download = item.name;
a.click();
URL.revokeObjectURL(blobUrl);
```

**After:**
```javascript
const a = document.createElement('a');
a.style.display = 'none';
a.href = blobUrl;
a.download = item.name;
document.body.appendChild(a);
a.click();
URL.revokeObjectURL(blobUrl);
a.remove();
```

- Element is now appended to `document.body` before `.click()` (matches the pattern used by `downloadFirebaseFile()`)
- Element is removed from DOM after click
- Hidden with `display: none` to prevent layout flash

### 3. Download All — Progress Feedback (`ui/index.html` ~line 5322)

**Added:**
- Button shows `Downloading 2/5...` counter during download
- Button is disabled while download is in progress (prevents double-click)
- Success alert: `Successfully downloaded 5 files.`
- Failure alert: `Downloaded 3 files. 2 failed.`
- Button text and state restore after completion (in `finally` block)

---

## Files Modified

| File | Lines Changed | Key Changes |
|---|---|---|
| `ui/index.html` | ~25 | History strip auto-expand, download DOM fix, download progress UI |
