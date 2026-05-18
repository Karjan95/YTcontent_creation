"""Renders the OAuth consent page.

Uses the same Firebase JS SDK config as the web UI — the page asks the user
to sign in (Google popup), obtains a Firebase ID token, and POSTs it to
/oauth/consent which exchanges it for an authorization code bound to the
client's PKCE challenge.
"""

import html
import json


def render_consent_page(*, client_id: str, client_name: str, redirect_uri: str,
                        state: str, code_challenge: str, code_challenge_method: str,
                        scope: str, firebase_config: dict) -> str:
    """Return an HTML page that handles the consent + sign-in flow."""
    safe_cfg = json.dumps(firebase_config)
    safe_client_id = html.escape(client_id)
    safe_client_name = html.escape(client_name or client_id)
    safe_redirect = html.escape(redirect_uri)
    safe_state = html.escape(state or "")
    safe_challenge = html.escape(code_challenge or "")
    safe_method = html.escape(code_challenge_method or "S256")
    safe_scope = html.escape(scope or "")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Connect Gemini Studio</title>
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'self'; script-src 'self' 'unsafe-inline' https://www.gstatic.com https://apis.google.com; script-src-elem 'self' 'unsafe-inline' https://www.gstatic.com https://apis.google.com; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://www.gstatic.com https://apis.google.com; img-src 'self' data: https:; frame-src https://*.firebaseapp.com https://apis.google.com https://accounts.google.com">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background:#0e0f12; color:#e8eaed; display:flex; align-items:center;
           justify-content:center; min-height:100vh; margin:0; }}
    .card {{ background:#181a20; border:1px solid #2a2d36; border-radius:16px;
            padding:32px; max-width:440px; width:100%; box-shadow:0 8px 24px rgba(0,0,0,.3); }}
    h1 {{ font-size:20px; margin:0 0 8px; }}
    p.lead {{ color:#9aa0a6; margin:0 0 20px; font-size:14px; line-height:1.5; }}
    .perms {{ background:#101218; border:1px solid #232733; border-radius:10px;
              padding:14px; margin:18px 0; font-size:13px; color:#cbd0d8; }}
    .perms li {{ margin:4px 0; }}
    button {{ width:100%; padding:12px; border:0; border-radius:10px;
              font-weight:600; font-size:14px; cursor:pointer; }}
    .btn-primary {{ background:#4285f4; color:#fff; margin-top:6px; }}
    .btn-primary:hover {{ background:#3367d6; }}
    .btn-primary:disabled {{ opacity:.6; cursor:not-allowed; }}
    .btn-secondary {{ background:transparent; color:#9aa0a6; margin-top:10px; }}
    .err {{ color:#f28b82; font-size:13px; margin-top:10px; min-height:18px; }}
    .signed {{ font-size:13px; color:#9aa0a6; margin:10px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Connect <em>{safe_client_name}</em> to Gemini Studio</h1>
    <p class="lead">This will allow the app to act on your behalf via the
       Studio MCP server. You can revoke access at any time.</p>
    <ul class="perms">
      <li>Generate images, videos, and audio with your Gemini and Kie API keys.</li>
      <li>Read and write your project asset library.</li>
      <li>Start and check Seedance animation sequences.</li>
    </ul>
    <div id="signed-as" class="signed" hidden></div>
    <button id="signin" class="btn-primary">Sign in with Google to continue</button>
    <button id="allow" class="btn-primary" hidden>Allow access</button>
    <button id="cancel" class="btn-secondary">Cancel</button>
    <div id="err" class="err" role="alert"></div>
  </div>

  <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
    import {{ getAuth, GoogleAuthProvider, signInWithPopup, onAuthStateChanged }}
      from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

    const cfg = {safe_cfg};
    const app = initializeApp(cfg);
    const auth = getAuth(app);

    const params = {{
      client_id: "{safe_client_id}",
      redirect_uri: "{safe_redirect}",
      state: "{safe_state}",
      code_challenge: "{safe_challenge}",
      code_challenge_method: "{safe_method}",
      scope: "{safe_scope}"
    }};

    const $signin = document.getElementById("signin");
    const $allow = document.getElementById("allow");
    const $cancel = document.getElementById("cancel");
    const $err = document.getElementById("err");
    const $signed = document.getElementById("signed-as");

    function showSigned(user) {{
      $signed.textContent = `Signed in as ${{user.email}}`;
      $signed.hidden = false;
      $signin.hidden = true;
      $allow.hidden = false;
    }}

    onAuthStateChanged(auth, (user) => {{
      if (user) showSigned(user);
    }});

    $signin.addEventListener("click", async () => {{
      $err.textContent = "";
      try {{
        const provider = new GoogleAuthProvider();
        const cred = await signInWithPopup(auth, provider);
        showSigned(cred.user);
      }} catch (e) {{
        $err.textContent = e.message || "Sign-in failed";
      }}
    }});

    $cancel.addEventListener("click", () => {{
      const u = new URL(params.redirect_uri);
      u.searchParams.set("error", "access_denied");
      if (params.state) u.searchParams.set("state", params.state);
      window.location.replace(u.toString());
    }});

    $allow.addEventListener("click", async () => {{
      $err.textContent = "";
      $allow.disabled = true;
      try {{
        const user = auth.currentUser;
        if (!user) throw new Error("Not signed in");
        const idToken = await user.getIdToken();
        const resp = await fetch("/oauth/consent", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            firebase_id_token: idToken,
            client_id: params.client_id,
            redirect_uri: params.redirect_uri,
            state: params.state,
            code_challenge: params.code_challenge,
            code_challenge_method: params.code_challenge_method,
            scope: params.scope
          }})
        }});
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.error_description || body.error || "Consent failed");
        window.location.replace(body.redirect);
      }} catch (e) {{
        $allow.disabled = false;
        $err.textContent = e.message || "Failed to complete consent";
      }}
    }});
  </script>
</body>
</html>"""
