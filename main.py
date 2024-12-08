import dotenv

from splat_replay import SplatReplay


if __name__ == '__main__':

    dotenv.load_dotenv()

    splat_replay = SplatReplay()
    splat_replay.run()