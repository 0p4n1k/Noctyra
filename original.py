import base64

print(''.join([i + 'a' for i in ['a', 'b']]))
# (
#     [
#         print(
#             (
#                 "".join(
#                     (
#                         chr(
#                             (ord(c) - (ord("A") if c.isupper() else ord("a")) - 8) % 26
#                             + (ord("A") if c.isupper() else ord("a"))
#                         )
#                         if c.isalpha()
#                         else c
#                     )
#                     for c in (
#                         "".join(
#                             (
#                                 chr(
#                                     (
#                                         ord(c)
#                                         - (ord("A") if c.isupper() else ord("a"))
#                                         - 100
#                                     )
#                                     % 26
#                                     + (ord("A") if c.isupper() else ord("a"))
#                                 )
#                                 if c.isalpha()
#                                 else c
#                             )
#                             for c in (
#                                 "".join(
#                                     (
#                                         chr(
#                                             (
#                                                 ord(c)
#                                                 - (
#                                                     ord("A")
#                                                     if c.isupper()
#                                                     else ord("a")
#                                                 )
#                                                 - 14
#                                             )
#                                             % 26
#                                             + (ord("A") if c.isupper() else ord("a"))
#                                         )
#                                         if c.isalpha()
#                                         else c
#                                     )
#                                     for c in (
#                                         "".join(
#                                             (
#                                                 chr(
#                                                     (
#                                                         ord(c)
#                                                         - (
#                                                             ord("A")
#                                                             if c.isupper()
#                                                             else ord("a")
#                                                         )
#                                                         - 31
#                                                     )
#                                                     % 26
#                                                     + (
#                                                         ord("A")
#                                                         if c.isupper()
#                                                         else ord("a")
#                                                     )
#                                                 )
#                                                 if c.isalpha()
#                                                 else c
#                                             )
#                                             for c in (
#                                                 "".join(
#                                                     (
#                                                         chr(
#                                                             (
#                                                                 ord(c)
#                                                                 - (
#                                                                     ord("A")
#                                                                     if c.isupper()
#                                                                     else ord("a")
#                                                                 )
#                                                                 - 34
#                                                             )
#                                                             % 26
#                                                             + (
#                                                                 ord("A")
#                                                                 if c.isupper()
#                                                                 else ord("a")
#                                                             )
#                                                         )
#                                                         if c.isalpha()
#                                                         else c
#                                                     )
#                                                     for c in (
#                                                         "".join(
#                                                             (
#                                                                 chr(
#                                                                     (
#                                                                         ord(c)
#                                                                         - (
#                                                                             ord("A")
#                                                                             if c.isupper()
#                                                                             else ord(
#                                                                                 "a"
#                                                                             )
#                                                                         )
#                                                                         - 29
#                                                                     )
#                                                                     % 26
#                                                                     + (
#                                                                         ord("A")
#                                                                         if c.isupper()
#                                                                         else ord("a")
#                                                                     )
#                                                                 )
#                                                                 if c.isalpha()
#                                                                 else c
#                                                             )
#                                                             for c in (
#                                                                 "".join(
#                                                                     (
#                                                                         chr(
#                                                                             (
#                                                                                 ord(c)
#                                                                                 - (
#                                                                                     ord(
#                                                                                         "A"
#                                                                                     )
#                                                                                     if c.isupper()
#                                                                                     else ord(
#                                                                                         "a"
#                                                                                     )
#                                                                                 )
#                                                                                 - 19
#                                                                             )
#                                                                             % 26
#                                                                             + (
#                                                                                 ord("A")
#                                                                                 if c.isupper()
#                                                                                 else ord(
#                                                                                     "a"
#                                                                                 )
#                                                                             )
#                                                                         )
#                                                                         if c.isalpha()
#                                                                         else c
#                                                                     )
#                                                                     for c in (
#                                                                         "".join(
#                                                                             (
#                                                                                 chr(
#                                                                                     (
#                                                                                         ord(
#                                                                                             c
#                                                                                         )
#                                                                                         - (
#                                                                                             ord(
#                                                                                                 "A"
#                                                                                             )
#                                                                                             if c.isupper()
#                                                                                             else ord(
#                                                                                                 "a"
#                                                                                             )
#                                                                                         )
#                                                                                         - 50
#                                                                                     )
#                                                                                     % 26
#                                                                                     + (
#                                                                                         ord(
#                                                                                             "A"
#                                                                                         )
#                                                                                         if c.isupper()
#                                                                                         else ord(
#                                                                                             "a"
#                                                                                         )
#                                                                                     )
#                                                                                 )
#                                                                                 if c.isalpha()
#                                                                                 else c
#                                                                             )
#                                                                             for c in (
#                                                                                 "".join(
#                                                                                     (
#                                                                                         chr(
#                                                                                             (
#                                                                                                 ord(
#                                                                                                     c
#                                                                                                 )
#                                                                                                 - (
#                                                                                                     ord(
#                                                                                                         "A"
#                                                                                                     )
#                                                                                                     if c.isupper()
#                                                                                                     else ord(
#                                                                                                         "a"
#                                                                                                     )
#                                                                                                 )
#                                                                                                 - 400
#                                                                                             )
#                                                                                             % 26
#                                                                                             + (
#                                                                                                 ord(
#                                                                                                     "A"
#                                                                                                 )
#                                                                                                 if c.isupper()
#                                                                                                 else ord(
#                                                                                                     "a"
#                                                                                                 )
#                                                                                             )
#                                                                                         )
#                                                                                         if c.isalpha()
#                                                                                         else c
#                                                                                     )
#                                                                                     for c in (
#                                                                                         "".join(
#                                                                                             (
#                                                                                                 chr(
#                                                                                                     (
#                                                                                                         ord(
#                                                                                                             c
#                                                                                                         )
#                                                                                                         - (
#                                                                                                             ord(
#                                                                                                                 "A"
#                                                                                                             )
#                                                                                                             if c.isupper()
#                                                                                                             else ord(
#                                                                                                                 "a"
#                                                                                                             )
#                                                                                                         )
#                                                                                                         - 18
#                                                                                                     )
#                                                                                                     % 26
#                                                                                                     + (
#                                                                                                         ord(
#                                                                                                             "A"
#                                                                                                         )
#                                                                                                         if c.isupper()
#                                                                                                         else ord(
#                                                                                                             "a"
#                                                                                                         )
#                                                                                                     )
#                                                                                                 )
#                                                                                                 if c.isalpha()
#                                                                                                 else c
#                                                                                             )
#                                                                                             for c in (
#                                                                                                 "".join(
#                                                                                                     (
#                                                                                                         chr(
#                                                                                                             (
#                                                                                                                 ord(
#                                                                                                                     c
#                                                                                                                 )
#                                                                                                                 - (
#                                                                                                                     ord(
#                                                                                                                         "A"
#                                                                                                                     )
#                                                                                                                     if c.isupper()
#                                                                                                                     else ord(
#                                                                                                                         "a"
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                                 - 4
#                                                                                                             )
#                                                                                                             % 26
#                                                                                                             + (
#                                                                                                                 ord(
#                                                                                                                     "A"
#                                                                                                                 )
#                                                                                                                 if c.isupper()
#                                                                                                                 else ord(
#                                                                                                                     "a"
#                                                                                                                 )
#                                                                                                             )
#                                                                                                         )
#                                                                                                         if c.isalpha()
#                                                                                                         else c
#                                                                                                     )
#                                                                                                     for c in (
#                                                                                                         "".join(
#                                                                                                             (
#                                                                                                                 chr(
#                                                                                                                     (
#                                                                                                                         ord(
#                                                                                                                             c
#                                                                                                                         )
#                                                                                                                         - (
#                                                                                                                             ord(
#                                                                                                                                 "A"
#                                                                                                                             )
#                                                                                                                             if c.isupper()
#                                                                                                                             else ord(
#                                                                                                                                 "a"
#                                                                                                                             )
#                                                                                                                         )
#                                                                                                                         - 32
#                                                                                                                     )
#                                                                                                                     % 26
#                                                                                                                     + (
#                                                                                                                         ord(
#                                                                                                                             "A"
#                                                                                                                         )
#                                                                                                                         if c.isupper()
#                                                                                                                         else ord(
#                                                                                                                             "a"
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                                 if c.isalpha()
#                                                                                                                 else c
#                                                                                                             )
#                                                                                                             for c in binascii.unhexlify(
#                                                                                                                 zlib.decompress(
#                                                                                                                     base64.b64decode(
#                                                                                                                         base64.b64decode(
#                                                                                                                             "ZUp3elNUWXpNVE0xTnpBek5qY3hUelMzTkRJd1N3YXlEWXdNekMzTkU4MU1nWHhEb0d5YWVhSlJzcEdCQ1l5TnFRck5IQUNKQkJSZQ==".encode(
#                                                                                                                                 "utf-8"
#                                                                                                                             )
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                             ).decode(
#                                                                                                                 "utf-8"
#                                                                                                             )
#                                                                                                         )
#                                                                                                     )
#                                                                                                     .encode(
#                                                                                                         "utf-8"
#                                                                                                     )
#                                                                                                     .decode(
#                                                                                                         "utf-8"
#                                                                                                     )
#                                                                                                 )
#                                                                                             )
#                                                                                             .encode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                             .decode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                         )
#                                                                                     )
#                                                                                     .encode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                     .decode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                 )
#                                                                             )
#                                                                             .encode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                             .decode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                         )
#                                                                     )
#                                                                     .encode("utf-8")
#                                                                     .decode("utf-8")
#                                                                 )
#                                                             )
#                                                             .encode("utf-8")
#                                                             .decode("utf-8")
#                                                         )
#                                                     )
#                                                     .encode("utf-8")
#                                                     .decode("utf-8")
#                                                 )
#                                             )
#                                             .encode("utf-8")
#                                             .decode("utf-8")
#                                         )
#                                     )
#                                     .encode("utf-8")
#                                     .decode("utf-8")
#                                 )
#                             )
#                             .encode("utf-8")
#                             .decode("utf-8")
#                         )
#                     )
#                     .encode("utf-8")
#                     .decode("utf-8")
#                 )
#             )
#             .encode("utf-8")
#             .decode("utf-8")
#         ),
#         print(
#             (
#                 "".join(
#                     (
#                         chr(
#                             (ord(c) - (ord("A") if c.isupper() else ord("a")) - 44) % 26
#                             + (ord("A") if c.isupper() else ord("a"))
#                         )
#                         if c.isalpha()
#                         else c
#                     )
#                     for c in (
#                         "".join(
#                             (
#                                 chr(
#                                     (
#                                         ord(c)
#                                         - (ord("A") if c.isupper() else ord("a"))
#                                         - 22
#                                     )
#                                     % 26
#                                     + (ord("A") if c.isupper() else ord("a"))
#                                 )
#                                 if c.isalpha()
#                                 else c
#                             )
#                             for c in (
#                                 "".join(
#                                     (
#                                         chr(
#                                             (
#                                                 ord(c)
#                                                 - (
#                                                     ord("A")
#                                                     if c.isupper()
#                                                     else ord("a")
#                                                 )
#                                                 - 32
#                                             )
#                                             % 26
#                                             + (ord("A") if c.isupper() else ord("a"))
#                                         )
#                                         if c.isalpha()
#                                         else c
#                                     )
#                                     for c in (
#                                         "".join(
#                                             (
#                                                 chr(
#                                                     (
#                                                         ord(c)
#                                                         - (
#                                                             ord("A")
#                                                             if c.isupper()
#                                                             else ord("a")
#                                                         )
#                                                         - 10000
#                                                     )
#                                                     % 26
#                                                     + (
#                                                         ord("A")
#                                                         if c.isupper()
#                                                         else ord("a")
#                                                     )
#                                                 )
#                                                 if c.isalpha()
#                                                 else c
#                                             )
#                                             for c in (
#                                                 "".join(
#                                                     (
#                                                         chr(
#                                                             (
#                                                                 ord(c)
#                                                                 - (
#                                                                     ord("A")
#                                                                     if c.isupper()
#                                                                     else ord("a")
#                                                                 )
#                                                                 - 20
#                                                             )
#                                                             % 26
#                                                             + (
#                                                                 ord("A")
#                                                                 if c.isupper()
#                                                                 else ord("a")
#                                                             )
#                                                         )
#                                                         if c.isalpha()
#                                                         else c
#                                                     )
#                                                     for c in (
#                                                         "".join(
#                                                             (
#                                                                 chr(
#                                                                     (
#                                                                         ord(c)
#                                                                         - (
#                                                                             ord("A")
#                                                                             if c.isupper()
#                                                                             else ord(
#                                                                                 "a"
#                                                                             )
#                                                                         )
#                                                                         - 13
#                                                                     )
#                                                                     % 26
#                                                                     + (
#                                                                         ord("A")
#                                                                         if c.isupper()
#                                                                         else ord("a")
#                                                                     )
#                                                                 )
#                                                                 if c.isalpha()
#                                                                 else c
#                                                             )
#                                                             for c in (
#                                                                 "".join(
#                                                                     (
#                                                                         chr(
#                                                                             (
#                                                                                 ord(c)
#                                                                                 - (
#                                                                                     ord(
#                                                                                         "A"
#                                                                                     )
#                                                                                     if c.isupper()
#                                                                                     else ord(
#                                                                                         "a"
#                                                                                     )
#                                                                                 )
#                                                                                 - 2000
#                                                                             )
#                                                                             % 26
#                                                                             + (
#                                                                                 ord("A")
#                                                                                 if c.isupper()
#                                                                                 else ord(
#                                                                                     "a"
#                                                                                 )
#                                                                             )
#                                                                         )
#                                                                         if c.isalpha()
#                                                                         else c
#                                                                     )
#                                                                     for c in (
#                                                                         "".join(
#                                                                             (
#                                                                                 chr(
#                                                                                     (
#                                                                                         ord(
#                                                                                             c
#                                                                                         )
#                                                                                         - (
#                                                                                             ord(
#                                                                                                 "A"
#                                                                                             )
#                                                                                             if c.isupper()
#                                                                                             else ord(
#                                                                                                 "a"
#                                                                                             )
#                                                                                         )
#                                                                                         - 50
#                                                                                     )
#                                                                                     % 26
#                                                                                     + (
#                                                                                         ord(
#                                                                                             "A"
#                                                                                         )
#                                                                                         if c.isupper()
#                                                                                         else ord(
#                                                                                             "a"
#                                                                                         )
#                                                                                     )
#                                                                                 )
#                                                                                 if c.isalpha()
#                                                                                 else c
#                                                                             )
#                                                                             for c in (
#                                                                                 "".join(
#                                                                                     (
#                                                                                         chr(
#                                                                                             (
#                                                                                                 ord(
#                                                                                                     c
#                                                                                                 )
#                                                                                                 - (
#                                                                                                     ord(
#                                                                                                         "A"
#                                                                                                     )
#                                                                                                     if c.isupper()
#                                                                                                     else ord(
#                                                                                                         "a"
#                                                                                                     )
#                                                                                                 )
#                                                                                                 - 350
#                                                                                             )
#                                                                                             % 26
#                                                                                             + (
#                                                                                                 ord(
#                                                                                                     "A"
#                                                                                                 )
#                                                                                                 if c.isupper()
#                                                                                                 else ord(
#                                                                                                     "a"
#                                                                                                 )
#                                                                                             )
#                                                                                         )
#                                                                                         if c.isalpha()
#                                                                                         else c
#                                                                                     )
#                                                                                     for c in (
#                                                                                         "".join(
#                                                                                             (
#                                                                                                 chr(
#                                                                                                     (
#                                                                                                         ord(
#                                                                                                             c
#                                                                                                         )
#                                                                                                         - (
#                                                                                                             ord(
#                                                                                                                 "A"
#                                                                                                             )
#                                                                                                             if c.isupper()
#                                                                                                             else ord(
#                                                                                                                 "a"
#                                                                                                             )
#                                                                                                         )
#                                                                                                         - 35
#                                                                                                     )
#                                                                                                     % 26
#                                                                                                     + (
#                                                                                                         ord(
#                                                                                                             "A"
#                                                                                                         )
#                                                                                                         if c.isupper()
#                                                                                                         else ord(
#                                                                                                             "a"
#                                                                                                         )
#                                                                                                     )
#                                                                                                 )
#                                                                                                 if c.isalpha()
#                                                                                                 else c
#                                                                                             )
#                                                                                             for c in (
#                                                                                                 "".join(
#                                                                                                     (
#                                                                                                         chr(
#                                                                                                             (
#                                                                                                                 ord(
#                                                                                                                     c
#                                                                                                                 )
#                                                                                                                 - (
#                                                                                                                     ord(
#                                                                                                                         "A"
#                                                                                                                     )
#                                                                                                                     if c.isupper()
#                                                                                                                     else ord(
#                                                                                                                         "a"
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                                 - 42
#                                                                                                             )
#                                                                                                             % 26
#                                                                                                             + (
#                                                                                                                 ord(
#                                                                                                                     "A"
#                                                                                                                 )
#                                                                                                                 if c.isupper()
#                                                                                                                 else ord(
#                                                                                                                     "a"
#                                                                                                                 )
#                                                                                                             )
#                                                                                                         )
#                                                                                                         if c.isalpha()
#                                                                                                         else c
#                                                                                                     )
#                                                                                                     for c in (
#                                                                                                         "".join(
#                                                                                                             (
#                                                                                                                 chr(
#                                                                                                                     (
#                                                                                                                         ord(
#                                                                                                                             c
#                                                                                                                         )
#                                                                                                                         - (
#                                                                                                                             ord(
#                                                                                                                                 "A"
#                                                                                                                             )
#                                                                                                                             if c.isupper()
#                                                                                                                             else ord(
#                                                                                                                                 "a"
#                                                                                                                             )
#                                                                                                                         )
#                                                                                                                         - 150
#                                                                                                                     )
#                                                                                                                     % 26
#                                                                                                                     + (
#                                                                                                                         ord(
#                                                                                                                             "A"
#                                                                                                                         )
#                                                                                                                         if c.isupper()
#                                                                                                                         else ord(
#                                                                                                                             "a"
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                                 if c.isalpha()
#                                                                                                                 else c
#                                                                                                             )
#                                                                                                             for c in zlib.decompress(
#                                                                                                                 base64.b85decode(
#                                                                                                                     base64.b64decode(
#                                                                                                                         base64.b64decode(
#                                                                                                                             "WXlVeFdFVkVjRll0VjBSd2VESStKbk5GTmtSRWIycHJVRkpNUkhSS1EwQlhOMlJ6V21oM1RrUWtWelJmSVRWU2VtMD0=".encode(
#                                                                                                                                 "utf-8"
#                                                                                                                             )
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                             ).decode(
#                                                                                                                 "utf-8"
#                                                                                                             )
#                                                                                                         )
#                                                                                                     )
#                                                                                                     .encode(
#                                                                                                         "utf-8"
#                                                                                                     )
#                                                                                                     .decode(
#                                                                                                         "utf-8"
#                                                                                                     )
#                                                                                                 )
#                                                                                             )
#                                                                                             .encode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                             .decode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                         )
#                                                                                     )
#                                                                                     .encode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                     .decode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                 )
#                                                                             )
#                                                                             .encode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                             .decode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                         )
#                                                                     )
#                                                                     .encode("utf-8")
#                                                                     .decode("utf-8")
#                                                                 )
#                                                             )
#                                                             .encode("utf-8")
#                                                             .decode("utf-8")
#                                                         )
#                                                     )
#                                                     .encode("utf-8")
#                                                     .decode("utf-8")
#                                                 )
#                                             )
#                                             .encode("utf-8")
#                                             .decode("utf-8")
#                                         )
#                                     )
#                                     .encode("utf-8")
#                                     .decode("utf-8")
#                                 )
#                             )
#                             .encode("utf-8")
#                             .decode("utf-8")
#                         )
#                     )
#                     .encode("utf-8")
#                     .decode("utf-8")
#                 )
#             )
#             .encode("utf-8")
#             .decode("utf-8")
#         ),
#         exit(1),
#     ][-1]
#     if globals()[
#         "__"
#         + (
#             "".join(
#                 (
#                     chr(
#                         (ord(c) - (ord("A") if c.isupper() else ord("a")) - 2000) % 26
#                         + (ord("A") if c.isupper() else ord("a"))
#                     )
#                     if c.isalpha()
#                     else c
#                 )
#                 for c in (
#                     "".join(
#                         (
#                             chr(
#                                 (ord(c) - (ord("A") if c.isupper() else ord("a")) - 15)
#                                 % 26
#                                 + (ord("A") if c.isupper() else ord("a"))
#                             )
#                             if c.isalpha()
#                             else c
#                         )
#                         for c in (
#                             "".join(
#                                 (
#                                     chr(
#                                         (
#                                             ord(c)
#                                             - (ord("A") if c.isupper() else ord("a"))
#                                             - 39
#                                         )
#                                         % 26
#                                         + (ord("A") if c.isupper() else ord("a"))
#                                     )
#                                     if c.isalpha()
#                                     else c
#                                 )
#                                 for c in (
#                                     "".join(
#                                         (
#                                             chr(
#                                                 (
#                                                     ord(c)
#                                                     - (
#                                                         ord("A")
#                                                         if c.isupper()
#                                                         else ord("a")
#                                                     )
#                                                     - 500
#                                                 )
#                                                 % 26
#                                                 + (
#                                                     ord("A")
#                                                     if c.isupper()
#                                                     else ord("a")
#                                                 )
#                                             )
#                                             if c.isalpha()
#                                             else c
#                                         )
#                                         for c in (
#                                             "".join(
#                                                 (
#                                                     chr(
#                                                         (
#                                                             ord(c)
#                                                             - (
#                                                                 ord("A")
#                                                                 if c.isupper()
#                                                                 else ord("a")
#                                                             )
#                                                             - 450
#                                                         )
#                                                         % 26
#                                                         + (
#                                                             ord("A")
#                                                             if c.isupper()
#                                                             else ord("a")
#                                                         )
#                                                     )
#                                                     if c.isalpha()
#                                                     else c
#                                                 )
#                                                 for c in (
#                                                     "".join(
#                                                         (
#                                                             chr(
#                                                                 (
#                                                                     ord(c)
#                                                                     - (
#                                                                         ord("A")
#                                                                         if c.isupper()
#                                                                         else ord("a")
#                                                                     )
#                                                                     - 40
#                                                                 )
#                                                                 % 26
#                                                                 + (
#                                                                     ord("A")
#                                                                     if c.isupper()
#                                                                     else ord("a")
#                                                                 )
#                                                             )
#                                                             if c.isalpha()
#                                                             else c
#                                                         )
#                                                         for c in (
#                                                             "".join(
#                                                                 (
#                                                                     chr(
#                                                                         (
#                                                                             ord(c)
#                                                                             - (
#                                                                                 ord("A")
#                                                                                 if c.isupper()
#                                                                                 else ord(
#                                                                                     "a"
#                                                                                 )
#                                                                             )
#                                                                             - 43
#                                                                         )
#                                                                         % 26
#                                                                         + (
#                                                                             ord("A")
#                                                                             if c.isupper()
#                                                                             else ord(
#                                                                                 "a"
#                                                                             )
#                                                                         )
#                                                                     )
#                                                                     if c.isalpha()
#                                                                     else c
#                                                                 )
#                                                                 for c in (
#                                                                     "".join(
#                                                                         (
#                                                                             chr(
#                                                                                 (
#                                                                                     ord(
#                                                                                         c
#                                                                                     )
#                                                                                     - (
#                                                                                         ord(
#                                                                                             "A"
#                                                                                         )
#                                                                                         if c.isupper()
#                                                                                         else ord(
#                                                                                             "a"
#                                                                                         )
#                                                                                     )
#                                                                                     - 50
#                                                                                 )
#                                                                                 % 26
#                                                                                 + (
#                                                                                     ord(
#                                                                                         "A"
#                                                                                     )
#                                                                                     if c.isupper()
#                                                                                     else ord(
#                                                                                         "a"
#                                                                                     )
#                                                                                 )
#                                                                             )
#                                                                             if c.isalpha()
#                                                                             else c
#                                                                         )
#                                                                         for c in (
#                                                                             "".join(
#                                                                                 (
#                                                                                     chr(
#                                                                                         (
#                                                                                             ord(
#                                                                                                 c
#                                                                                             )
#                                                                                             - (
#                                                                                                 ord(
#                                                                                                     "A"
#                                                                                                 )
#                                                                                                 if c.isupper()
#                                                                                                 else ord(
#                                                                                                     "a"
#                                                                                                 )
#                                                                                             )
#                                                                                             - 49
#                                                                                         )
#                                                                                         % 26
#                                                                                         + (
#                                                                                             ord(
#                                                                                                 "A"
#                                                                                             )
#                                                                                             if c.isupper()
#                                                                                             else ord(
#                                                                                                 "a"
#                                                                                             )
#                                                                                         )
#                                                                                     )
#                                                                                     if c.isalpha()
#                                                                                     else c
#                                                                                 )
#                                                                                 for c in (
#                                                                                     "".join(
#                                                                                         (
#                                                                                             chr(
#                                                                                                 (
#                                                                                                     ord(
#                                                                                                         c
#                                                                                                     )
#                                                                                                     - (
#                                                                                                         ord(
#                                                                                                             "A"
#                                                                                                         )
#                                                                                                         if c.isupper()
#                                                                                                         else ord(
#                                                                                                             "a"
#                                                                                                         )
#                                                                                                     )
#                                                                                                     - 22
#                                                                                                 )
#                                                                                                 % 26
#                                                                                                 + (
#                                                                                                     ord(
#                                                                                                         "A"
#                                                                                                     )
#                                                                                                     if c.isupper()
#                                                                                                     else ord(
#                                                                                                         "a"
#                                                                                                     )
#                                                                                                 )
#                                                                                             )
#                                                                                             if c.isalpha()
#                                                                                             else c
#                                                                                         )
#                                                                                         for c in (
#                                                                                             "".join(
#                                                                                                 (
#                                                                                                     chr(
#                                                                                                         (
#                                                                                                             ord(
#                                                                                                                 c
#                                                                                                             )
#                                                                                                             - (
#                                                                                                                 ord(
#                                                                                                                     "A"
#                                                                                                                 )
#                                                                                                                 if c.isupper()
#                                                                                                                 else ord(
#                                                                                                                     "a"
#                                                                                                                 )
#                                                                                                             )
#                                                                                                             - 19
#                                                                                                         )
#                                                                                                         % 26
#                                                                                                         + (
#                                                                                                             ord(
#                                                                                                                 "A"
#                                                                                                             )
#                                                                                                             if c.isupper()
#                                                                                                             else ord(
#                                                                                                                 "a"
#                                                                                                             )
#                                                                                                         )
#                                                                                                     )
#                                                                                                     if c.isalpha()
#                                                                                                     else c
#                                                                                                 )
#                                                                                                 for c in (
#                                                                                                     "".join(
#                                                                                                         (
#                                                                                                             chr(
#                                                                                                                 (
#                                                                                                                     ord(
#                                                                                                                         c
#                                                                                                                     )
#                                                                                                                     - (
#                                                                                                                         ord(
#                                                                                                                             "A"
#                                                                                                                         )
#                                                                                                                         if c.isupper()
#                                                                                                                         else ord(
#                                                                                                                             "a"
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                     - 20
#                                                                                                                 )
#                                                                                                                 % 26
#                                                                                                                 + (
#                                                                                                                     ord(
#                                                                                                                         "A"
#                                                                                                                     )
#                                                                                                                     if c.isupper()
#                                                                                                                     else ord(
#                                                                                                                         "a"
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                             )
#                                                                                                             if c.isalpha()
#                                                                                                             else c
#                                                                                                         )
#                                                                                                         for c in marshal.loads(
#                                                                                                             base64.b64decode(
#                                                                                                                 zlib.decompress(
#                                                                                                                     base64.b64decode(
#                                                                                                                         "eJxLTU8JCcy2DAzKrvABABw2BEw=".encode(
#                                                                                                                             "utf-8"
#                                                                                                                         )
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                             )
#                                                                                                         )
#                                                                                                     )
#                                                                                                 )
#                                                                                                 .encode(
#                                                                                                     "utf-8"
#                                                                                                 )
#                                                                                                 .decode(
#                                                                                                     "utf-8"
#                                                                                                 )
#                                                                                             )
#                                                                                         )
#                                                                                         .encode(
#                                                                                             "utf-8"
#                                                                                         )
#                                                                                         .decode(
#                                                                                             "utf-8"
#                                                                                         )
#                                                                                     )
#                                                                                 )
#                                                                                 .encode(
#                                                                                     "utf-8"
#                                                                                 )
#                                                                                 .decode(
#                                                                                     "utf-8"
#                                                                                 )
#                                                                             )
#                                                                         )
#                                                                         .encode("utf-8")
#                                                                         .decode("utf-8")
#                                                                     )
#                                                                 )
#                                                                 .encode("utf-8")
#                                                                 .decode("utf-8")
#                                                             )
#                                                         )
#                                                         .encode("utf-8")
#                                                         .decode("utf-8")
#                                                     )
#                                                 )
#                                                 .encode("utf-8")
#                                                 .decode("utf-8")
#                                             )
#                                         )
#                                         .encode("utf-8")
#                                         .decode("utf-8")
#                                     )
#                                 )
#                                 .encode("utf-8")
#                                 .decode("utf-8")
#                             )
#                         )
#                         .encode("utf-8")
#                         .decode("utf-8")
#                     )
#                 )
#                 .encode("utf-8")
#                 .decode("utf-8")
#             )
#         )
#         .encode("utf-8")
#         .decode("utf-8")
#         + "__"
#     ]
#     != (
#         "".join(
#             (
#                 chr(
#                     (ord(c) - (ord("A") if c.isupper() else ord("a")) - 42) % 26
#                     + (ord("A") if c.isupper() else ord("a"))
#                 )
#                 if c.isalpha()
#                 else c
#             )
#             for c in (
#                 "".join(
#                     (
#                         chr(
#                             (ord(c) - (ord("A") if c.isupper() else ord("a")) - 41) % 26
#                             + (ord("A") if c.isupper() else ord("a"))
#                         )
#                         if c.isalpha()
#                         else c
#                     )
#                     for c in (
#                         "".join(
#                             (
#                                 chr(
#                                     (
#                                         ord(c)
#                                         - (ord("A") if c.isupper() else ord("a"))
#                                         - 30
#                                     )
#                                     % 26
#                                     + (ord("A") if c.isupper() else ord("a"))
#                                 )
#                                 if c.isalpha()
#                                 else c
#                             )
#                             for c in (
#                                 "".join(
#                                     (
#                                         chr(
#                                             (
#                                                 ord(c)
#                                                 - (
#                                                     ord("A")
#                                                     if c.isupper()
#                                                     else ord("a")
#                                                 )
#                                                 - 16
#                                             )
#                                             % 26
#                                             + (ord("A") if c.isupper() else ord("a"))
#                                         )
#                                         if c.isalpha()
#                                         else c
#                                     )
#                                     for c in (
#                                         "".join(
#                                             (
#                                                 chr(
#                                                     (
#                                                         ord(c)
#                                                         - (
#                                                             ord("A")
#                                                             if c.isupper()
#                                                             else ord("a")
#                                                         )
#                                                         - 13
#                                                     )
#                                                     % 26
#                                                     + (
#                                                         ord("A")
#                                                         if c.isupper()
#                                                         else ord("a")
#                                                     )
#                                                 )
#                                                 if c.isalpha()
#                                                 else c
#                                             )
#                                             for c in (
#                                                 "".join(
#                                                     (
#                                                         chr(
#                                                             (
#                                                                 ord(c)
#                                                                 - (
#                                                                     ord("A")
#                                                                     if c.isupper()
#                                                                     else ord("a")
#                                                                 )
#                                                                 - 6
#                                                             )
#                                                             % 26
#                                                             + (
#                                                                 ord("A")
#                                                                 if c.isupper()
#                                                                 else ord("a")
#                                                             )
#                                                         )
#                                                         if c.isalpha()
#                                                         else c
#                                                     )
#                                                     for c in (
#                                                         "".join(
#                                                             (
#                                                                 chr(
#                                                                     (
#                                                                         ord(c)
#                                                                         - (
#                                                                             ord("A")
#                                                                             if c.isupper()
#                                                                             else ord(
#                                                                                 "a"
#                                                                             )
#                                                                         )
#                                                                         - 10000
#                                                                     )
#                                                                     % 26
#                                                                     + (
#                                                                         ord("A")
#                                                                         if c.isupper()
#                                                                         else ord("a")
#                                                                     )
#                                                                 )
#                                                                 if c.isalpha()
#                                                                 else c
#                                                             )
#                                                             for c in (
#                                                                 "".join(
#                                                                     (
#                                                                         chr(
#                                                                             (
#                                                                                 ord(c)
#                                                                                 - (
#                                                                                     ord(
#                                                                                         "A"
#                                                                                     )
#                                                                                     if c.isupper()
#                                                                                     else ord(
#                                                                                         "a"
#                                                                                     )
#                                                                                 )
#                                                                                 - 50
#                                                                             )
#                                                                             % 26
#                                                                             + (
#                                                                                 ord("A")
#                                                                                 if c.isupper()
#                                                                                 else ord(
#                                                                                     "a"
#                                                                                 )
#                                                                             )
#                                                                         )
#                                                                         if c.isalpha()
#                                                                         else c
#                                                                     )
#                                                                     for c in (
#                                                                         "".join(
#                                                                             (
#                                                                                 chr(
#                                                                                     (
#                                                                                         ord(
#                                                                                             c
#                                                                                         )
#                                                                                         - (
#                                                                                             ord(
#                                                                                                 "A"
#                                                                                             )
#                                                                                             if c.isupper()
#                                                                                             else ord(
#                                                                                                 "a"
#                                                                                             )
#                                                                                         )
#                                                                                         - 47
#                                                                                     )
#                                                                                     % 26
#                                                                                     + (
#                                                                                         ord(
#                                                                                             "A"
#                                                                                         )
#                                                                                         if c.isupper()
#                                                                                         else ord(
#                                                                                             "a"
#                                                                                         )
#                                                                                     )
#                                                                                 )
#                                                                                 if c.isalpha()
#                                                                                 else c
#                                                                             )
#                                                                             for c in (
#                                                                                 "".join(
#                                                                                     (
#                                                                                         chr(
#                                                                                             (
#                                                                                                 ord(
#                                                                                                     c
#                                                                                                 )
#                                                                                                 - (
#                                                                                                     ord(
#                                                                                                         "A"
#                                                                                                     )
#                                                                                                     if c.isupper()
#                                                                                                     else ord(
#                                                                                                         "a"
#                                                                                                     )
#                                                                                                 )
#                                                                                                 - 32
#                                                                                             )
#                                                                                             % 26
#                                                                                             + (
#                                                                                                 ord(
#                                                                                                     "A"
#                                                                                                 )
#                                                                                                 if c.isupper()
#                                                                                                 else ord(
#                                                                                                     "a"
#                                                                                                 )
#                                                                                             )
#                                                                                         )
#                                                                                         if c.isalpha()
#                                                                                         else c
#                                                                                     )
#                                                                                     for c in (
#                                                                                         "".join(
#                                                                                             (
#                                                                                                 chr(
#                                                                                                     (
#                                                                                                         ord(
#                                                                                                             c
#                                                                                                         )
#                                                                                                         - (
#                                                                                                             ord(
#                                                                                                                 "A"
#                                                                                                             )
#                                                                                                             if c.isupper()
#                                                                                                             else ord(
#                                                                                                                 "a"
#                                                                                                             )
#                                                                                                         )
#                                                                                                         - 35
#                                                                                                     )
#                                                                                                     % 26
#                                                                                                     + (
#                                                                                                         ord(
#                                                                                                             "A"
#                                                                                                         )
#                                                                                                         if c.isupper()
#                                                                                                         else ord(
#                                                                                                             "a"
#                                                                                                         )
#                                                                                                     )
#                                                                                                 )
#                                                                                                 if c.isalpha()
#                                                                                                 else c
#                                                                                             )
#                                                                                             for c in (
#                                                                                                 "".join(
#                                                                                                     (
#                                                                                                         chr(
#                                                                                                             (
#                                                                                                                 ord(
#                                                                                                                     c
#                                                                                                                 )
#                                                                                                                 - (
#                                                                                                                     ord(
#                                                                                                                         "A"
#                                                                                                                     )
#                                                                                                                     if c.isupper()
#                                                                                                                     else ord(
#                                                                                                                         "a"
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                                 - 44
#                                                                                                             )
#                                                                                                             % 26
#                                                                                                             + (
#                                                                                                                 ord(
#                                                                                                                     "A"
#                                                                                                                 )
#                                                                                                                 if c.isupper()
#                                                                                                                 else ord(
#                                                                                                                     "a"
#                                                                                                                 )
#                                                                                                             )
#                                                                                                         )
#                                                                                                         if c.isalpha()
#                                                                                                         else c
#                                                                                                     )
#                                                                                                     for c in zlib.decompress(
#                                                                                                         base64.b64decode(
#                                                                                                             base64.b85decode(
#                                                                                                                 base64.b64decode(
#                                                                                                                     "V2xESFZPPUwtV0t8dyk3Ylowfns=".encode(
#                                                                                                                         "utf-8"
#                                                                                                                     )
#                                                                                                                 )
#                                                                                                             )
#                                                                                                         )
#                                                                                                     ).decode(
#                                                                                                         "utf-8"
#                                                                                                     )
#                                                                                                 )
#                                                                                             )
#                                                                                             .encode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                             .decode(
#                                                                                                 "utf-8"
#                                                                                             )
#                                                                                         )
#                                                                                     )
#                                                                                     .encode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                     .decode(
#                                                                                         "utf-8"
#                                                                                     )
#                                                                                 )
#                                                                             )
#                                                                             .encode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                             .decode(
#                                                                                 "utf-8"
#                                                                             )
#                                                                         )
#                                                                     )
#                                                                     .encode("utf-8")
#                                                                     .decode("utf-8")
#                                                                 )
#                                                             )
#                                                             .encode("utf-8")
#                                                             .decode("utf-8")
#                                                         )
#                                                     )
#                                                     .encode("utf-8")
#                                                     .decode("utf-8")
#                                                 )
#                                             )
#                                             .encode("utf-8")
#                                             .decode("utf-8")
#                                         )
#                                     )
#                                     .encode("utf-8")
#                                     .decode("utf-8")
#                                 )
#                             )
#                             .encode("utf-8")
#                             .decode("utf-8")
#                         )
#                     )
#                     .encode("utf-8")
#                     .decode("utf-8")
#                 )
#             )
#             .encode("utf-8")
#             .decode("utf-8")
#         )
#     )
#     .encode("utf-8")
#     .decode("utf-8")
#     else None
# )
