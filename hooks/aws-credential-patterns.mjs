// High-confidence AWS credential detection shared by the current-release supplements.
// This closes the ASIA (temporary STS access-key ID) gap without altering the immutable
// workshop-installer release pinned by configs/secrets-guard.manifest.json.

// The immutable pinned canonical release already owns AKIA. Keep this supplement disjoint so
// Claude never receives two competing updatedToolOutput rewrites for the same value.
const ACCESS_KEY_ID = /\bASIA[0-9A-Z]{16}\b/g;
const NAMED = [
  {
    name: "AWS secret access key",
    re: /(\b(?:AWS_SECRET_ACCESS_KEY|aws_secret_access_key|SecretAccessKey)\b["']?\s*(?:=|:)\s*["']?)([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])/gi,
  },
  {
    name: "AWS session token",
    re: /(\b(?:AWS_SESSION_TOKEN|aws_session_token|SessionToken)\b["']?\s*(?:=|:)\s*["']?)([A-Za-z0-9/+=]{80,})(?![A-Za-z0-9/+=])/gi,
  },
  {
    name: "AWS secret access key",
    re: /(\baws\s+configure\s+set\s+aws_secret_access_key\s+)([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])/gi,
  },
  {
    name: "AWS session token",
    re: /(\baws\s+configure\s+set\s+aws_session_token\s+)([A-Za-z0-9/+=]{80,})(?![A-Za-z0-9/+=])/gi,
  },
];

function highConfidence(value) {
  if (!value || /placeholder|paste|example|sample|dummy|changeme|replace|your[_-]/i.test(value)) return false;
  if (/^(.)\1+$/.test(value)) return false;
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[+/=]/].filter((re) => re.test(value)).length;
  return classes >= 3 && new Set(value).size >= 10;
}

export function findAwsCredential(text) {
  const source = String(text ?? "");
  ACCESS_KEY_ID.lastIndex = 0;
  if (ACCESS_KEY_ID.test(source)) return "AWS access key id";
  for (const pattern of NAMED) {
    pattern.re.lastIndex = 0;
    let match;
    while ((match = pattern.re.exec(source)) !== null) {
      if (highConfidence(match[2])) return pattern.name;
    }
  }
  return null;
}

function redactText(text, hits) {
  let redacted = text;
  ACCESS_KEY_ID.lastIndex = 0;
  redacted = redacted.replace(ACCESS_KEY_ID, () => {
    hits.add("AWS access key id");
    return "[REDACTED: AWS access key id]";
  });
  for (const pattern of NAMED) {
    pattern.re.lastIndex = 0;
    redacted = redacted.replace(pattern.re, (match, prefix, credential) => {
      if (!highConfidence(credential)) return match;
      hits.add(pattern.name);
      return `${prefix}[REDACTED: ${pattern.name}]`;
    });
  }
  return redacted;
}

export function redactAwsCredentials(value) {
  const hits = new Set();
  const visit = (item) => {
    if (typeof item === "string") return redactText(item, hits);
    if (Array.isArray(item)) return item.map(visit);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.entries(item).map(([key, child]) => [key, visit(child)]));
    }
    return item;
  };
  return { value: visit(value), names: [...hits] };
}
