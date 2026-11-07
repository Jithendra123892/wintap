"""Tests for feature toggle system."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from wintap import features


class TestFeatureMetadata(unittest.TestCase):
    """Test feature metadata and indexing."""

    def test_feature_metadata_exists(self):
        """All features have metadata."""
        self.assertTrue(len(features.FEATURE_METADATA) > 0)
        self.assertEqual(len(features.FEATURE_METADATA), 22)

    def test_feature_names_unique(self):
        """All feature names are unique."""
        names = [f["name"] for f in features.FEATURE_METADATA]
        self.assertEqual(len(names), len(set(names)))

    def test_feature_index_mapping(self):
        """Feature index mapping is correct."""
        for f in features.FEATURE_METADATA:
            self.assertEqual(features.FEATURE_INDEX[f["name"]], f["index"])

    def test_get_feature_by_name(self):
        """Looking up existing feature returns correct metadata."""
        feat = features.get_feature_by_name("twist_direction")
        self.assertIsNotNone(feat)
        self.assertEqual(feat["label"], "Twist Direction")
        self.assertEqual(feat["importance"], "essential")

    def test_get_nonexistent_feature(self):
        """Looking up nonexistent feature returns None."""
        feat = features.get_feature_by_name("nonexistent")
        self.assertIsNone(feat)

    def test_default_enabled_features(self):
        """Default enabled features are properly set."""
        self.assertTrue(len(features.DEFAULT_ENABLED_FEATURES) > 0)
        # Essential features should be in defaults
        self.assertIn("twist_direction", features.DEFAULT_ENABLED_FEATURES)


class TestFeatureCategories(unittest.TestCase):
    """Test feature categories."""

    def test_categories_exist(self):
        """Required categories exist."""
        self.assertIn("core", features.FEATURE_CATEGORIES)
        self.assertIn("spectral", features.FEATURE_CATEGORIES)
        self.assertIn("template", features.FEATURE_CATEGORIES)

    def test_category_structure(self):
        """Each category has required fields."""
        for name, data in features.FEATURE_CATEGORIES.items():
            self.assertIn("label", data)
            self.assertIn("desc", data)
            self.assertIn("features", data)
            self.assertTrue(len(data["features"]) > 0)

    def test_core_features_count(self):
        """Core features count is 8."""
        count = len(features.FEATURE_CATEGORIES["core"]["features"])
        self.assertEqual(count, 8)

    def test_spectral_features_count(self):
        """Spectral features count is 12."""
        count = len(features.FEATURE_CATEGORIES["spectral"]["features"])
        self.assertEqual(count, 12)

    def test_template_features_count(self):
        """Template features count is 2."""
        count = len(features.FEATURE_CATEGORIES["template"]["features"])
        self.assertEqual(count, 2)


class TestFeatureValidation(unittest.TestCase):
    """Test feature validation logic."""

    def test_feature_names_valid(self):
        """All feature names match expected indices."""
        for f in features.FEATURE_METADATA:
            idx = f["index"]
            name_idx_map = {f2["index"]: f2["name"] for f2 in features.FEATURE_METADATA}
            self.assertEqual(name_idx_map[idx], f["name"])

    def test_importance_values(self):
        """Importance values are valid."""
        valid_importance = {"essential", "useful", "experimental"}
        for f in features.FEATURE_METADATA:
            self.assertIn(f["importance"], valid_importance)


if __name__ == "__main__":
    unittest.main()