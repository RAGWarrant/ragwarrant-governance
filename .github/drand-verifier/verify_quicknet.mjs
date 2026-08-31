import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import {
  fetchBeacon,
  HttpCachingChain,
  HttpChainClient,
} from "drand-client";

const ENTROPY_PROTOCOL = "DRAND_QUICKNET_FUTURE_ROUND_V1";
const CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971";
const PUBLIC_KEY = "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a";
const GENESIS_TIME = 1692803367;
const PERIOD_SECONDS = 3;
const SCHEME = "bls-unchained-g1-rfc9380";
const BEACON_ID = "quicknet";
const PACKAGE_VERSION = "1.4.2";
const PACKAGE_INTEGRITY = "sha512-jeNJmrVplfgIA/GVndxxJ5mo8y63BS2pEdNhk1siU4pQ+z/BnxsqRnxjH9ag1ip887s12SEgo0MTZPbQNz27NA==";
const RELAYS = [
  `https://api.drand.sh/${CHAIN_HASH}`,
  `https://drand.cloudflare.com/${CHAIN_HASH}`,
];

function fail(message) {
  throw new Error(message);
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      fail("arguments must be --name value pairs");
    }
    result[key.slice(2)] = value;
  }
  for (const required of ["seal", "seal-publication", "output"]) {
    if (!result[required]) fail(`missing --${required}`);
  }
  return result;
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function exactPinnedInfo(info) {
  return (
    info?.metadata?.beaconID === BEACON_ID &&
    info?.hash === CHAIN_HASH &&
    info?.public_key === PUBLIC_KEY &&
    info?.genesis_time === GENESIS_TIME &&
    info?.period === PERIOD_SECONDS &&
    info?.schemeID === SCHEME
  );
}

function validateSeal(seal) {
  if (seal?.schema_version !== "1.0") fail("unsupported seal schema");
  if (seal?.entropy_protocol !== ENTROPY_PROTOCOL) fail("entropy protocol mismatch");
  if (seal?.seal_status !== "SEALED_PENDING_BEACON") fail("seal is not pending beacon");
  if (seal?.seed_schedule_version !== 2) fail("seed schedule version mismatch");
  if (seal?.no_fallback_round !== true) fail("seal permits a fallback round");
  if (seal?.automatic_result_publication !== true) fail("seal does not require publication");
  if (seal?.full_executed !== false) fail("original seal must remain unexecuted");
  if (!exactPinnedInfo({
    metadata: { beaconID: seal?.drand?.beacon_id },
    hash: seal?.drand?.chain_hash,
    public_key: seal?.drand?.public_key,
    genesis_time: seal?.drand?.genesis_time,
    period: seal?.drand?.period_seconds,
    schemeID: seal?.drand?.scheme,
  })) fail("seal Quicknet parameters are not pinned values");
  const round = seal?.drand?.target_round;
  if (!Number.isSafeInteger(round) || round < 1) fail("sealed round is invalid");
  const scheduled = GENESIS_TIME + (round - 1) * PERIOD_SECONDS;
  if (Date.parse(seal?.drand?.target_round_timestamp_utc) !== scheduled * 1000) {
    fail("sealed round timestamp mismatch");
  }
  const started = Date.parse(seal?.seal_workflow_started_at_utc) / 1000;
  if (!Number.isInteger(started)) fail("seal workflow start timestamp is invalid");
  const expectedRound = Math.ceil((started + 1800 - GENESIS_TIME) / PERIOD_SECONDS) + 1;
  if (round !== Math.max(1, expectedRound)) {
    fail("seal did not select the first round at least 30 minutes after workflow start");
  }
  return { round, scheduled };
}

function validateSealPublication(seal, publication) {
  const sealSha256 = sha256Hex(Buffer.from(`${canonicalJson(seal)}\n`, "utf8"));
  const expectedBranch = `ragwarrant-full-seal-${seal.subject_commit}`;
  if (publication?.schema_version !== "1.0") fail("unsupported seal publication schema");
  if (publication?.subject_commit !== seal.subject_commit) fail("seal publication subject mismatch");
  if (publication?.seal_sha256 !== sealSha256) fail("seal publication does not bind the exact seal bytes");
  if (!/^[0-9a-f]{40}$/.test(publication?.seal_commit_sha ?? "")) {
    fail("seal publication commit is invalid");
  }
  if (publication?.canonical_seal_branch !== expectedBranch) fail("canonical seal branch mismatch");
  if (publication?.canonical_seal_ref !== `refs/heads/${expectedBranch}`) {
    fail("canonical seal ref mismatch");
  }
  if (!/^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/.test(publication?.draft_pr_url ?? "")) {
    fail("seal PR URL is not a GitHub pull request URL");
  }
  const publishedAt = Date.parse(publication?.github_created_at_utc);
  if (!Number.isFinite(publishedAt)) fail("seal PR timestamp is invalid");
  return { sealSha256, publishedAt };
}

async function verifiedRelayResponse(relayUrl, targetRound) {
  const options = {
    disableBeaconVerification: false,
    noCache: true,
    chainVerificationParams: { chainHash: CHAIN_HASH, publicKey: PUBLIC_KEY },
  };
  const chain = new HttpCachingChain(relayUrl, options);
  const info = await chain.info();
  if (!exactPinnedInfo(info)) fail(`relay metadata mismatch: ${relayUrl}`);
  const client = new HttpChainClient(chain, options);
  const beacon = await fetchBeacon(client, targetRound);
  if (beacon.round !== targetRound) fail(`relay returned wrong round: ${relayUrl}`);
  if (!/^[0-9a-f]{64}$/.test(beacon.randomness)) fail("invalid randomness encoding");
  if (!/^[0-9a-f]+$/.test(beacon.signature) || beacon.signature.length % 2 !== 0) {
    fail("invalid signature encoding");
  }
  if (sha256Hex(Buffer.from(beacon.signature, "hex")) !== beacon.randomness) {
    fail("randomness is not SHA-256(signature)");
  }
  return {
    relay_url: relayUrl,
    round: beacon.round,
    response_sha256: sha256Hex(Buffer.from(canonicalJson(beacon), "utf8")),
    signature_verified: true,
    randomness: beacon.randomness,
    signature: beacon.signature,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const seal = JSON.parse(await readFile(args.seal, "utf8"));
  const publication = JSON.parse(await readFile(args["seal-publication"], "utf8"));
  const { round, scheduled } = validateSeal(seal);
  const { sealSha256, publishedAt } = validateSealPublication(seal, publication);
  if (Date.now() < scheduled * 1000) fail("sealed round is not available yet");
  if (!Number.isFinite(publishedAt) || publishedAt >= scheduled * 1000) {
    fail("draft seal PR was not public before the sealed round");
  }

  const responses = [];
  for (const relay of RELAYS) {
    responses.push(await verifiedRelayResponse(relay, round));
  }
  const [first, ...others] = responses;
  if (others.some((item) => item.randomness !== first.randomness || item.signature !== first.signature)) {
    fail("independently verified relay responses disagree");
  }

  const receipt = {
    schema_version: "1.0",
    entropy_protocol: ENTROPY_PROTOCOL,
    verification_status: "VERIFIED",
    signature_verified: true,
    subject_commit: seal.subject_commit,
    benchmark_freeze_digest: seal.benchmark_freeze_digest,
    seal_sha256: sealSha256,
    verified_at_utc: new Date().toISOString(),
    verifier: {
      package: "drand-client",
      version: PACKAGE_VERSION,
      integrity: PACKAGE_INTEGRITY,
      beacon_verification_disabled: false,
    },
    drand: {
      beacon_id: BEACON_ID,
      chain_hash: CHAIN_HASH,
      public_key: PUBLIC_KEY,
      genesis_time: GENESIS_TIME,
      period_seconds: PERIOD_SECONDS,
      scheme: SCHEME,
      round,
      randomness: first.randomness,
      signature: first.signature,
    },
    relay_verifications: responses.map(({ randomness, signature, ...record }) => record),
    seal_publication: publication,
    full_master_seed_persisted: false,
  };
  await writeFile(args.output, `${JSON.stringify(receipt, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });
}

main().catch((error) => {
  console.error(`drand verification failed: ${error.message}`);
  process.exitCode = 1;
});
