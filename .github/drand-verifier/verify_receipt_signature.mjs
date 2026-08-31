import { readFile } from "node:fs/promises";
import { fetchBeacon } from "drand-client";

const receiptPath = process.argv[2];
if (!receiptPath) throw new Error("usage: verify_receipt_signature.mjs <receipt>");
const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
const drand = receipt.drand;
const chainInfo = {
  public_key: drand.public_key,
  period: drand.period_seconds,
  genesis_time: drand.genesis_time,
  hash: drand.chain_hash,
  groupHash: "",
  schemeID: drand.scheme,
  metadata: { beaconID: drand.beacon_id },
};
const beacon = {
  round: drand.round,
  randomness: drand.randomness,
  signature: drand.signature,
};
const chain = { info: async () => chainInfo };
const client = {
  options: {
    disableBeaconVerification: false,
    noCache: true,
    chainVerificationParams: {
      chainHash: chainInfo.hash,
      publicKey: chainInfo.public_key,
    },
  },
  chain: () => chain,
  get: async (round) => {
    if (round !== beacon.round) throw new Error("receipt round mismatch");
    return beacon;
  },
};
await fetchBeacon(client, beacon.round);
process.stdout.write("receipt BLS signature verified\n");
