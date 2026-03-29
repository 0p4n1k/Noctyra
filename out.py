import base64


def run():
    payload = "cHJpbnQoIiIuam9pbihjaHIoeCkgZm9yIHggaW4gWzcyLCAxMDEsIDEwOCwgMTA4LCAxMTEsIDMyLCAxMDIsIDExNCwgMTExLCAxMDksIDMyLCA3OCwgMTExLCA5OSwgMTE2LCAxMjEsIDExNCwgOTcsIDMzXSkp"
    exec(base64.b64decode(payload).decode())


if __name__ == "__main__":
    run()
