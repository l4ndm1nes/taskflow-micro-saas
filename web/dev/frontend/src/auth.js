export function makeAuth(config) {
  const {
    domain,
    clientId,
    redirectUri,
    scopes = ["openid", "email", "profile"],
  } = config;

  const LS = { id: "tf_id_token", at: "tf_access_token", rt: "tf_refresh_token" };
  const SS = { verifier: "tf_code_verifier", state: "tf_oauth_state" };

  const base64url = (buf) =>
    btoa(String.fromCharCode(...new Uint8Array(buf)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");

  const randomString = (len = 64) => {
    const a = new Uint8Array(len);
    crypto.getRandomValues(a);
    return base64url(a).slice(0, len);
  };

  const sha256 = async (str) => {
    const data = new TextEncoder().encode(str);
    return await crypto.subtle.digest("SHA-256", data);
  };

  const saveTokens = (json) => {
    if (json.id_token) localStorage.setItem(LS.id, json.id_token);
    if (json.access_token) localStorage.setItem(LS.at, json.access_token);
    if (json.refresh_token) localStorage.setItem(LS.rt, json.refresh_token);
  };

  const clearTokens = () => {
    localStorage.removeItem(LS.id);
    localStorage.removeItem(LS.at);
    localStorage.removeItem(LS.rt);
  };

  const getIdToken = () => localStorage.getItem(LS.id) || "";

  async function signIn() {
    const state = randomString(32);
    sessionStorage.setItem(SS.state, state);

    const code_verifier = randomString(96);
    sessionStorage.setItem(SS.verifier, code_verifier);
    const code_challenge = base64url(await sha256(code_verifier));

    const u = new URL(`https://${domain}/oauth2/authorize`);
    u.searchParams.set("response_type", "code");
    u.searchParams.set("client_id", clientId);
    u.searchParams.set("redirect_uri", redirectUri);
    u.searchParams.set("scope", scopes.join(" "));
    u.searchParams.set("state", state);
    u.searchParams.set("code_challenge_method", "S256");
    u.searchParams.set("code_challenge", code_challenge);

    window.location.assign(u.toString());
  }

  async function handleRedirectCallback() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    if (!code) return false;

    const savedState = sessionStorage.getItem(SS.state);
    if (!savedState || savedState !== state) return false;

    const code_verifier = sessionStorage.getItem(SS.verifier) || "";

    const tokenUrl = `https://${domain}/oauth2/token`;
    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: clientId,
      code,
      redirect_uri: redirectUri,
      code_verifier,
    });

    const resp = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    if (!resp.ok) throw new Error(`Token exchange failed: ${resp.status} ${await resp.text()}`);
    const json = await resp.json();
    saveTokens(json);

    window.history.replaceState({}, "", window.location.origin + window.location.pathname);
    return json;
  }

  function signOut() {
    clearTokens();
    const u = new URL(`https://${domain}/logout`);
    u.searchParams.set("client_id", clientId);
    u.searchParams.set("logout_uri", redirectUri);
    window.location.assign(u.toString());
  }

  return { getIdToken, signIn, signOut, handleRedirectCallback };
}
