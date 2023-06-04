def cprint(text: str, color: str = "green"):
    color_text = "\033[92m"
    reset_text = "\033[0m"
    if color == "red":
        color_text = "\033[91m"

    print(f"{color_text}{text}{reset_text}")
