# How to set up the Bright Data API key

This project uses Bright Data’s **API key** (Bearer token) to call the **Datasets API** (e.g. Facebook Marketplace). Use the same key for trigger, progress, and snapshot download. Follow these steps to create or reuse the correct type of key.

---

## 1. Sign in to Bright Data

1. Go to **https://brightdata.com** and sign in.
2. You must use an **admin** account. Only admins can create or manage API keys. If you don’t see the API key section, switch to an admin user.

---

## 2. Open Account settings (API keys)

1. In the Bright Data control panel, open **Account settings**.
2. Direct link: **https://brightdata.com/cp/setting/users**
3. Find the **“API key”** section on the page (often near the top or under a “Users” / “Security” area).

---

## 3. Create or locate your API key

### Option A: You already have an API key

- Bright Data creates a **default API key** when the account is set up. It may be listed in Account settings.
- **Important:** Bright Data does **not** show the key value again after creation. If you didn’t save it, you must create a new key (Option B) and revoke the old one if needed.

### Option B: Create a new API key

1. Click **“Add API key”** (top right of the API key section).
2. If the button is missing, you’re not on an admin account—switch to one.
3. **Configure the key:**
   - **User:** Choose the user this key will act as (usually yourself or a dedicated “API” user).
   - **Permissions:** For triggering and downloading datasets (e.g. Facebook Marketplace), use at least:
     - **User** – API usage on zone/product level (enough to call the Datasets API), or  
     - **Ops** – if you also need to change product/dataset configuration, or  
     - **Admin** – full access (only if you need it).
   - **Expiration:** Set a date or **Unlimited**. Bright Data recommends setting an expiration; choose what fits your security policy.
4. Click **Save**.
5. **Copy and store the key immediately.** It is shown **only once**. Store it in a password manager or your `.env` file (and never commit `.env` to git).

---

## 4. Use the key in this project

1. In the project root, copy the example env file (if you haven’t already):
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and set (use the name you prefer):
   ```bash
   BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY=<paste-your-key-here>
   ```
   The script also accepts `BRIGHTDATA_API_KEY` as a fallback.
3. Optionally set:
   ```bash
   LISTINGS_DB=listings.db
   BRIGHTDATA_DATASET_ID=gd_lvt9iwuh6fbcwmx1a
   BRIGHTDATA_KEYWORD=Apartment
   BRIGHTDATA_CITY=Provo
   ```
4. Save the file. Ensure `.env` is in `.gitignore` and **never commit it**.
5. Run the scraper + downloader:
   ```bash
   python scrape.py
   python scrape_download.py
   ```

---

## 5. Confirm it’s the right “type” of key

- **Product:** This key is for **API Access** (not proxy username/password). The same key is used for:
  - **Datasets / Marketplace** (trigger, progress, snapshot download)
  - Other Bright Data API products that use Bearer auth
- **Authentication:** Requests must send:
  ```http
  Authorization: Bearer <your-api-key>
  ```
  The project’s `fetch.py` does this automatically using `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` (or `BRIGHTDATA_API_KEY`).
- If you get **401 Unauthorized**, the key is wrong, expired, or revoked. Create a new key in Account settings and update `.env`.

---

## 6. For GitHub Actions (CI)

- Do **not** put the key in the repo. Use **GitHub Secrets**:
  1. Repo → **Settings** → **Secrets and variables** → **Actions**
  2. **New repository secret**
  3. Name: `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY` (or `BRIGHTDATA_API_KEY`)
  4. Value: your Bright Data API key
- In the workflow, pass it as an env var (e.g. `env: BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY: ${{ secrets.BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY }}`).

---

## Summary

| Step | Action |
|------|--------|
| 1 | Sign in at brightdata.com (admin account) |
| 2 | Go to https://brightdata.com/cp/setting/users |
| 3 | Click **Add API key** (or use existing key if you have it saved) |
| 4 | Set User, Permissions (e.g. User or Ops), Expiration → Save |
| 5 | Copy the key once and store it securely |
| 6 | Put it in `.env` as `BRIGHT_DATA_FACEBOOK_MARKETPLACE_API_KEY=...` (or in GitHub Secrets for CI) |

This is the only type of API key you need for the Datasets/Marketplace trigger and snapshot APIs used by this project.
