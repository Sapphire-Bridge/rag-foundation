export const PASSWORD_MAX_BYTES = 72; // matches backend bcrypt guard; adjust if auth provider changes

export const validatePassword = (pwd: string) => {
  const encoder = new TextEncoder();
  const byteLength = encoder.encode(pwd).length;

  const checks = [
    { valid: pwd.length >= 8, msg: "Min 8 chars" },
    { valid: byteLength <= PASSWORD_MAX_BYTES, msg: "Max 72 bytes" },
    { valid: /[A-Z]/.test(pwd), msg: "1 Uppercase" },
    { valid: /[a-z]/.test(pwd), msg: "1 Lowercase" },
    { valid: /[0-9]/.test(pwd), msg: "1 Number" },
    { valid: /[!@#$%^&*(),.?\":{}|<>]/.test(pwd), msg: "1 Special Char" },
  ];

  const isValid = checks.every((c) => c.valid);
  return { isValid, checks };
};
