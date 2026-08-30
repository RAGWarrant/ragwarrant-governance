import { readFile } from "node:fs/promises";
import { fetchBeacon } from "drand-client";

const fixturePath = process.argv[2];
const mode = process.argv[3] ?? "valid";
if (!fixturePath || !["valid", "tampered"].includes(mode)) {
  throw new Error("usage: verify_historical_fixture.mjs <fixture> [valid|tampered]");
}

const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const beacon = structuredClone(fixture.beacon);
if (mode === "tampered") {
  beacon.signature = `${beacon.signature.slice(0, -1)}${beacon.signature.endsWith("0") ? "1" : "0"}`;
}
const chain = { info: async () => fixture.chain_info };
const client = {
  options: {
    disableBeaconVerification: false,
    noCache: true,
    chainVerificationParams: {
      chainHash: fixture.chain_info.hash,
      publicKey: fixture.chain_info.public_key,
    },
  },
  chain: () => chain,
  get: async (round) => {
    if (round !== beacon.round) throw new Error("fixture round mismatch");
    return beacon;
  },
};

try {
  const verified = await fetchBeacon(client, beacon.round);
  if (mode === "tampered") throw new Error("tampered signature was accepted");
  if (verified.randomness !== beacon.randomness) throw new Error("verified randomness mismatch");
  process.stdout.write("historical Quicknet signature verified\n");
} catch (error) {
  if (mode === "tampered") {
    process.stdout.write("tampered historical signature rejected\n");
  } else {
    throw error;
  }
}
