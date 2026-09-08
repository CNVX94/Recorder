import unittest
import numpy as np

from recorder.audio.processing import bars, rms, to_16k


class TestAudioProcessing(unittest.TestCase):
    def test_rms(self):
        silence = np.zeros(1024, dtype=np.int16)
        self.assertEqual(rms(silence), 0.0)

        tone = np.full(1024, 1000, dtype=np.int16)
        self.assertAlmostEqual(rms(tone), 1000.0, places=2)

    def test_bars(self):
        self.assertEqual(bars(0), "░" * 8)
        self.assertEqual(bars(32768), "█" * 8)
        # Log scale check (-40 dB should be 2 blocks)
        self.assertEqual(bars(327.68), "██░░░░░░")

    def test_to_16k_resampling(self):
        # 48000 Hz, estéreo (2 canales), 1 segundo = 48000 * 2 muestras
        pcm = np.zeros(48000 * 2, dtype=np.int16)
        resampled = to_16k(pcm, rate=48000, channels=2)

        self.assertEqual(resampled.shape, (16000,))
        self.assertEqual(resampled.dtype, np.float32)


if __name__ == "__main__":
    unittest.main()
