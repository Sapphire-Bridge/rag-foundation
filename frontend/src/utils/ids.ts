// Generates an RFC 4122 v4 UUID using Web Crypto.
// Throws if a secure random source is unavailable to avoid silent downgrade.
export const secureRandomId = () => {
  const cryptoObj = globalThis.crypto;
  if (!cryptoObj) throw new Error("Secure random generator unavailable");
  if (cryptoObj.randomUUID) return cryptoObj.randomUUID();

  const bytes = new Uint8Array(16);
  cryptoObj.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant RFC4122
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return `${hex[0]}${hex[1]}${hex[2]}${hex[3]}-${hex[4]}${hex[5]}-${hex[6]}${hex[7]}-${hex[8]}${hex[9]}-${hex[10]}${hex[11]}${hex[12]}${hex[13]}${hex[14]}${hex[15]}`;
};
