import modal


app = modal.App("nomad-compute-check")


@app.function()
def nomad_hello(name="Nomad"):
    import platform

    return f"Hello from {name} on Modal! Running on {platform.platform()} with {platform.processor()}"


def run_check():
    print("Checking Modal credentials and SDK...")
    try:
        with app.run():
            result = nomad_hello.remote("Nomad Agent")
            print(f"Result: {result}")
            print("Modal compute lane is ACTIVE and verified.")
    except Exception as e:
        print(f"Modal check failed: {e}")
        print("Tip: Run 'python -m modal setup' to configure your credentials.")


if __name__ == "__main__":
    run_check()
