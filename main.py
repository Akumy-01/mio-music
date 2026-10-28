import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from mio.smoke import run
        sys.exit(run(sys.argv[2]))
    from mio.ui import main
    main()
