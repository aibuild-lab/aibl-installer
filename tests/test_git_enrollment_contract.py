"""Current Git destination must not rewrite the immutable-package interface."""
import json, unittest
from pathlib import Path

class GitEnrollmentContract(unittest.TestCase):
    def test_current_target_and_legacy_identity_are_separate(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/"course-options.json").read_text())
        row=next(p for p in registry["programs"] if p["id"]=="agent-workforce")
        self.assertEqual(row["enrollment"],{"repository":"aibuild-lab/agent-workforce","branch":"student","skill":"aibl-enroll"})
        self.assertEqual((row["publisher"],row["release_product"],row["adopt_skill"]),("aibuild-lab/agent-native-workforce","agent-native-workforce","aibl-adopt-workforce"))
