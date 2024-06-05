const SECRET_KEY = "thisisasecretofus";

export function decodeVideoUrl(encoded: string): string {
  const decoded = atob(encoded);
  const key = SECRET_KEY;
  let result = "";
  for (let i = 0; i < decoded.length; i++) {
    result += String.fromCharCode(decoded.charCodeAt(i) ^ key.charCodeAt(i % key.length));
  }
  return result;
}
