import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--lyrics-smoke-test':
        from mio.smoke import run_lyrics
        sys.exit(run_lyrics(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from mio.smoke import run
        sys.exit(run(sys.argv[2]))
    from mio.ui import main
    main()
