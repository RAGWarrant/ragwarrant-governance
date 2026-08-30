import { createPublicKey, verify } from "node:crypto";

const [subjectCommit, sealSha256] = process.argv.slice(2);
const repository = "RAGWarrant/ragwarrant-governance";
if (!/^[0-9a-f]{40}$/.test(subjectCommit ?? "")) throw new Error("invalid frozen subject commit");
if (!/^[0-9a-f]{64}$/.test(sealSha256 ?? "")) throw new Error("invalid seal digest");
const requestUrl = process.env.ACTIONS_ID_TOKEN_REQUEST_URL;
const requestToken = process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN;
if (!requestUrl || !requestToken) throw new Error("GitHub Actions OIDC capability is unavailable");
const parsedRequest = new URL(requestUrl);
if (parsedRequest.protocol !== "https:" || !parsedRequest.hostname.endsWith(".actions.githubusercontent.com")) {
  throw new Error("untrusted GitHub OIDC request endpoint");
}
const audience = `ragwarrant-full:${subjectCommit}:${sealSha256}`;
parsedRequest.searchParams.set("audience", audience);
const tokenResponse = await fetch(parsedRequest, {
  headers: { Authorization: `Bearer ${requestToken}` },
});
if (!tokenResponse.ok) throw new Error(`GitHub OIDC token request failed: ${tokenResponse.status}`);
const token = (await tokenResponse.json()).value;
const parts = token?.split(".");
if (!parts || parts.length !== 3) throw new Error("GitHub OIDC token is malformed");
const header = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
const claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
if (header.alg !== "RS256" || typeof header.kid !== "string") throw new Error("unsupported GitHub OIDC signing key");
const discoveryUrl = "https://token.actions.githubusercontent.com/.well-known/openid-configuration";
const discovery = await (await fetch(discoveryUrl)).json();
if (discovery.issuer !== "https://token.actions.githubusercontent.com") throw new Error("GitHub OIDC issuer discovery mismatch");
if (new URL(discovery.jwks_uri).hostname !== "token.actions.githubusercontent.com") throw new Error("GitHub OIDC JWKS host mismatch");
const jwks = await (await fetch(discovery.jwks_uri)).json();
const jwk = jwks.keys?.find((candidate) => candidate.kid === header.kid);
if (!jwk) throw new Error("GitHub OIDC signing key was not found");
const signatureValid = verify(
  "RSA-SHA256",
  Buffer.from(`${parts[0]}.${parts[1]}`, "ascii"),
  createPublicKey({ key: jwk, format: "jwk" }),
  Buffer.from(parts[2], "base64url"),
);
if (!signatureValid) throw new Error("GitHub OIDC signature verification failed");
const now = Math.floor(Date.now() / 1000);
if (claims.iss !== discovery.issuer || claims.aud !== audience) throw new Error("GitHub OIDC issuer or audience mismatch");
if (!Number.isInteger(claims.exp) || claims.exp <= now || (Number.isInteger(claims.nbf) && claims.nbf > now)) {
  throw new Error("GitHub OIDC token is outside its validity interval");
}
if (claims.repository !== repository) throw new Error("GitHub OIDC repository mismatch");
if (claims.sha !== subjectCommit) throw new Error("GitHub OIDC commit mismatch");
if (claims.ref !== `refs/heads/ragwarrant-full-subject-${subjectCommit}`) throw new Error("GitHub OIDC frozen ref mismatch");
if (claims.workflow !== "Research FULL future-beacon execution") throw new Error("GitHub OIDC workflow mismatch");
if (claims.event_name !== "workflow_dispatch") throw new Error("GitHub OIDC event mismatch");
if (!/^[0-9]+$/.test(String(claims.run_id ?? ""))) throw new Error("GitHub OIDC run ID is invalid");
process.stdout.write(`${JSON.stringify({github_oidc_execution_verified:true,repository,ref:claims.ref,sha:claims.sha,workflow:claims.workflow,run_id:String(claims.run_id)})}\n`);
