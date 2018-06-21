def cp(source, dest):
    if dest.endswith('/'):
        dest = ''.join((dest, source.split('/')[-1]))  # cp /sd/file /fc/
    with open(source, 'rb') as infile:
        with open(dest, 'wb') as outfile:
            while True:
                buf = infile.read(100)
                outfile.write(buf)
                if len(buf) < 100:
                    break