# Phase 3: Auto-Sync with Drive Changes API

## 🎯 Overview

ระบบ Auto-sync ช่วยให้รูปภาพใหม่ที่อัปโหลดเข้า Google Drive folder ถูก index อัตโนมัติ โดยไม่ต้องกด "Start Indexing" ใหม่ทุกครั้ง

### ✨ Features

- ✅ **Auto-detect new photos** - ตรวจจับรูปใหม่อัตโนมัติทุก 1-2 นาті
- ✅ **Incremental indexing** - Index เฉพาะรูปใหม่ ไม่ซ้ำ
- ✅ **Configurable interval** - ปรับช่วงเวลาเช็คได้ (1-60 นาที)
- ✅ **Background processing** - ทำงาน background ไม่กระทบ UI
- ✅ **Enable/Disable anytime** - เปิด/ปิดได้ทุกเมื่อ

---

## 📊 How It Works

```
[Google Drive] → [Changes API] → [Auto-sync Thread] → [Face Indexing] → [Database]
       ↓                ↓                ↓                    ↓              ↓
   New photo     Check every      Index only         Extract faces    Store results
   uploaded        2 min          new photos
```

### Process Flow:

1. **Photographer enables auto-sync** for an event
2. **Background thread starts** checking for changes every N minutes
3. **Drive Changes API** returns list of new files
4. **System downloads and indexes** only new photos
5. **Face encodings saved** to database automatically
6. **Event stats updated** (total photos, total faces)

---

## 🚀 Getting Started

### 1. Run Database Migration

Before using auto-sync, update your database:

```bash
# Method 1: Using Python script
python run_migration.py

# Method 2: Using sqlite3 (if available)
sqlite3 database.db < migration_phase3_auto_sync.sql
```

### 2. Configure Auto-sync Interval (Optional)

Add to `.env` file:

```bash
# Check for new photos every N minutes (default: 2)
AUTO_SYNC_INTERVAL=2
```

### 3. Enable Auto-sync via API

```bash
# Enable auto-sync with default interval (2 minutes)
curl -X POST http://localhost:5000/api/event/{event_id}/auto-sync/enable \
  -H "Content-Type: application/json" \
  -d '{"interval_minutes": 2}'

# Disable auto-sync
curl -X POST http://localhost:5000/api/event/{event_id}/auto-sync/disable

# Check status
curl http://localhost:5000/api/event/{event_id}/auto-sync/status
```

---

## 📡 API Endpoints

### Enable Auto-sync

**POST** `/api/event/{event_id}/auto-sync/enable`

Request body (optional):
```json
{
  "interval_minutes": 2
}
```

Response:
```json
{
  "message": "Auto-sync enabled",
  "interval_minutes": 2
}
```

### Disable Auto-sync

**POST** `/api/event/{event_id}/auto-sync/disable`

Response:
```json
{
  "message": "Auto-sync disabled"
}
```

### Get Status

**GET** `/api/event/{event_id}/auto-sync/status`

Response:
```json
{
  "enabled": true,
  "running": true,
  "interval_minutes": 2,
  "last_sync_at": "2025-12-03T10:30:00"
}
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SYNC_INTERVAL` | `2` | Default check interval in minutes |

### Interval Limits

- **Minimum:** 1 minute (safety limit: 30 seconds)
- **Maximum:** No limit (but recommended ≤ 60 minutes)
- **Recommended:** 1-5 minutes for active events

---

## 💾 Database Schema

### New Columns in `events` table:

```sql
drive_start_page_token TEXT      -- Track Drive changes
auto_sync_enabled INTEGER        -- 1 = enabled, 0 = disabled
last_sync_at TIMESTAMP           -- Last successful sync time
sync_interval_minutes INTEGER    -- Check interval
```

### New Table: `synced_photos`

```sql
CREATE TABLE synced_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,
    photo_name TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, photo_id)
);
```

Purpose: Track which photos have been indexed to avoid duplicates.

---

## 🔄 Usage Scenarios

### Scenario 1: Live Event Photography

```
1. Create event and link Drive folder
2. Enable auto-sync with 1-minute interval
3. Photographer uploads photos during event
4. System auto-indexes new photos every minute
5. Guests can search and find their photos immediately
```

### Scenario 2: Post-Event Batch Upload

```
1. Create event and link Drive folder
2. Run initial indexing manually
3. Enable auto-sync with 5-minute interval
4. Additional photos uploaded later are auto-indexed
5. No need to manually re-index
```

### Scenario 3: Multiple Events

```
1. Each event can have independent auto-sync settings
2. Different intervals per event
3. Enable/disable independently
4. No performance impact
```

---

## 🎛️ How to Use (Frontend Integration)

### Add Toggle Button to Dashboard

```html
<!-- In photographer_dashboard.html -->
<button onclick="toggleAutoSync('{{event.id}}')">
  <span id="sync-status-{{event.id}}">Auto-sync: OFF</span>
</button>
```

### JavaScript Example

```javascript
async function toggleAutoSync(eventId) {
  // Get current status
  const status = await fetch(`/api/event/${eventId}/auto-sync/status`);
  const data = await status.json();

  if (data.enabled) {
    // Disable
    await fetch(`/api/event/${eventId}/auto-sync/disable`, { method: 'POST' });
    showToast('Auto-sync disabled', 'info');
  } else {
    // Enable with 2-minute interval
    await fetch(`/api/event/${eventId}/auto-sync/enable`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval_minutes: 2 })
    });
    showToast('Auto-sync enabled (checks every 2 minutes)', 'success');
  }

  // Refresh UI
  updateSyncStatus(eventId);
}
```

---

## 📝 Logs

Auto-sync activities are logged to `logs/app.log`:

```
[2025-12-03 10:30:00] INFO - Starting auto-sync loop for event abc-123 (interval: 2 min)
[2025-12-03 10:32:00] INFO - Found 3 new photo(s) for event abc-123
[2025-12-03 10:32:15] INFO - Auto-sync completed: 3 photos, 5 faces
[2025-12-03 10:34:00] DEBUG - No new photos for event abc-123
```

---

## ⚠️ Limitations & Notes

### Current Limitations:

1. **Session-based credentials** - Auto-sync threads cannot auto-restore after server restart
   - Workaround: Photographer needs to re-enable after server restart

2. **Single-threaded per event** - One sync thread per event
   - Not a problem: Each event gets its own thread

3. **Polling-based** - Not true real-time
   - Trade-off: Simpler implementation, good enough for most use cases
   - Alternative: Webhook-based push notifications (complex setup)

### Best Practices:

- ✅ Use 1-2 minute intervals for live events
- ✅ Use 5-10 minute intervals for casual events
- ✅ Disable auto-sync when event is done
- ✅ Monitor logs for errors
- ❌ Don't set interval < 1 minute (API rate limits)

---

## 🐛 Troubleshooting

### Auto-sync not working?

1. **Check logs:**
   ```bash
   tail -f logs/app.log | grep auto-sync
   ```

2. **Verify status:**
   ```bash
   curl http://localhost:5000/api/event/{event_id}/auto-sync/status
   ```

3. **Check credentials:**
   - Ensure user is logged in with Google OAuth
   - Credentials must have `refresh_token`

4. **Restart auto-sync:**
   ```bash
   # Disable then enable again
   curl -X POST http://localhost:5000/api/event/{event_id}/auto-sync/disable
   curl -X POST http://localhost:5000/api/event/{event_id}/auto-sync/enable
   ```

### Common Errors:

| Error | Cause | Solution |
|-------|-------|----------|
| "Invalid page token" | Token expired or corrupted | System auto-resets token |
| "Not authenticated" | No session credentials | Re-login with Google |
| "Already running" | Thread still active | Disable then enable again |

---

## 🚀 Performance

### Impact on System:

- **CPU:** Minimal (sleeps between checks)
- **RAM:** ~10-20MB per active thread
- **Network:** 1 API call every N minutes
- **Database:** Incremental inserts only

### Scaling:

- **10 events:** No problem
- **100 events:** Still fine
- **1000+ events:** Consider rate limiting

---

## 🔮 Future Enhancements

Potential improvements for Phase 4:

- [ ] Webhook-based push notifications (true real-time)
- [ ] Persistent credential storage (auto-restore threads)
- [ ] Batch processing optimization
- [ ] Rate limit handling
- [ ] Retry logic for failed syncs
- [ ] Email notifications on new photos
- [ ] Dashboard widget showing sync activity

---

## 📚 Related Documentation

- [Google Drive Changes API](https://developers.google.com/drive/api/v3/reference/changes)
- [Google Drive Push Notifications](https://developers.google.com/drive/api/v3/push)
- [Face Recognition Library](https://face-recognition.readthedocs.io/)

---

## ✅ Testing Checklist

Before deploying to production:

- [ ] Database migration completed
- [ ] Auto-sync enabled for test event
- [ ] Upload new photo to Drive folder
- [ ] Verify photo appears in database within interval
- [ ] Check logs for errors
- [ ] Test disable functionality
- [ ] Test multiple events simultaneously
- [ ] Test server restart behavior

---

**Status:** ✅ Implemented in Phase 3
**Version:** 1.0.0
**Last Updated:** 2025-12-03
