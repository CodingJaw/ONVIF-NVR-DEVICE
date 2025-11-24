import unittest
from tempfile import TemporaryDirectory

from src.config import ConfigManager, MediaSourceType
from src.media_pipeline import MediaPipelineManager


class MediaPipelineRestartTestCase(unittest.TestCase):
    def test_profile_update_restarts_running_pipeline(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config = ConfigManager(tmpdir)
            manager = MediaPipelineManager(config, rtsp_host="localhost")

            manager.get_stream_uri("profile1")
            instance = manager._pipelines["profile1"]
            original_pipeline = instance.last_pipeline

            manager.set_profile_parameters(
                "profile1",
                width=640,
                height=480,
                framerate=25,
                source_type=MediaSourceType.testscreen,
            )

            self.assertTrue(instance.running)
            self.assertNotEqual(instance.last_pipeline, original_pipeline)
            self.assertIn("width=640", instance.last_pipeline)
            self.assertIn("height=480", instance.last_pipeline)
            self.assertIn("framerate=25/1", instance.last_pipeline)
            self.assertIn("videotestsrc", instance.last_pipeline)


if __name__ == "__main__":
    unittest.main()
