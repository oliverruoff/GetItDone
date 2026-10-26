"""Fresh interpreter establishes controlling tty before exec; no fork hooks in Qt process."""

import fcntl
import os
import sys
import termios


def main():
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()
