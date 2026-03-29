import base64

e = "".join(
    chr((ord(ch) - ord("a") - 13) % 26 + ord("a"))
    if "a" <= ch <= "z"
    else chr((ord(ch) - ord("A") - 13) % 26 + ord("A"))
    if "A" <= ch <= "Z"
    else ch
    for ch in base64.b64decode(
        "".join([chr(ord(i) ^ 36) for i in "r|n\x11AsmWmcTM~|H\\mga\x19"])
    ).decode()
)
