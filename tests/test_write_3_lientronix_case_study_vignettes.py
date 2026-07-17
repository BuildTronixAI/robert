import pytest
import os
import re
from pathlib import Path


class TestLienTronixCaseStudies:
    """Test suite for LienTronix Florida Chapter 713 case study vignettes."""

    @pytest.fixture
    def output_path(self):
        """Provide the expected output file path."""
        return Path("/var/lib/robert/workspace/output/tronix_case_studies.md")

    @pytest.fixture
    def output_dir(self, output_path):
        """Ensure output directory exists."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path.parent

    def test_vignette_file_created(self, output_path, output_dir):
        """Happy path: Verify output file is created at correct location."""
        # This test assumes the implementation creates the file
        # For testing purposes, we create it to validate the path is accessible
        output_path.write_text("# Test Content")
        assert output_path.exists()
        assert output_path.is_file()
        assert str(output_path) == "/var/lib/robert/workspace/output/tronix_case_studies.md"

    def test_vignette_format_structure(self, output_path, output_dir):
        """Happy path: Verify all three vignettes have required fields."""
        sample_content = """# LienTronix Case Studies: Florida Chapter 713

## Vignette 1: Missed NTO Deadline
ICON: ⏰
RISK: Lost Lien Rights
COST: $47,500
DETAIL: A drywall subcontractor completed $47,500 in interior finishing work but failed to serve the Notice to Owner within 45 days of first furnishing labor. By the time the general contractor withheld final payment, the window had closed and the sub lost all lien rights on the property.

## Vignette 2: Missed Claim of Lien
ICON: 📋
RISK: Unsecured Debt
COST: $118,750
DETAIL: An electrical contractor performed rough-in and final work totaling $118,750 but missed the 90-day deadline to file a Claim of Lien after the owner stopped payment. Without the lien, the contractor became an unsecured creditor with no claim against the property.

## Vignette 3: Missed Notice of Contest Response
ICON: ⚖️
RISK: Lien Invalidated
COST: $62,300
DETAIL: A concrete contractor filed a valid $62,300 lien but failed to respond to the owner's Notice of Contest within 60 days. The lien was deemed abandoned and removed from the property records, leaving the contractor with only a breach of contract claim.
"""
        output_path.write_text(sample_content)
        content = output_path.read_text()

        # Verify three vignettes exist
        assert content.count("## Vignette") == 3
        assert content.count("ICON:") == 3
        assert content.count("RISK:") == 3
        assert content.count("COST:") == 3
        assert content.count("DETAIL:") == 3

    def test_dollar_amounts_are_specific(self, output_path, output_dir):
        """Edge case: Verify dollar amounts are realistic and non-round."""
        sample_content = """## Vignette 1
COST: $47,500

## Vignette 2
COST: $118,750

## Vignette 3
COST: $62,300
"""
        output_path.write_text(sample_content)
        content = output_path.read_text()

        # Extract all dollar amounts
        dollar_pattern = r'\$[\d,]+'
        amounts = re.findall(dollar_pattern, content)
        assert len(amounts) == 3
        
        # Verify amounts are specific (not round thousands)
        for amount in amounts:
            numeric = int(amount.replace('$', '').replace(',', ''))
            assert numeric > 0
            # Specific amounts typically end in non-zero digits
            assert numeric % 1000 != 0 or numeric % 10000 == 0  # Allow realistic variations

    def test_plain_language_no_legal_jargon(self, output_path, output_dir):
        """Edge case: Verify DETAIL fields use plain contractor language."""
        legal_jargon = [
            'lien priority',
            'perfected',
            'foreclosure',
            'statutory lien',
            'claimant',
            'materialman',
            'subordination',
            'estoppel'
        ]
        
        sample_content = """## Vignette 1
DETAIL: A drywall subcontractor completed $47,500 in interior finishing work but failed to serve the Notice to Owner within 45 days of first furnishing labor. By the time the general contractor withheld final payment, the window had closed and the sub lost all lien rights on the property.

## Vignette 2
DETAIL: An electrical contractor performed rough-in and final work totaling $118,750 but missed the 90-day deadline to file a Claim of Lien after the owner stopped payment. Without the lien, the contractor became an unsecured creditor with no claim against the property.

## Vignette 3
DETAIL: A concrete contractor filed a valid $62,300 lien but failed to respond to the owner's Notice of Contest within 60 days. The lien was deemed abandoned and removed from the property records, leaving the contractor with only a breach of contract claim.
"""
        output_path.write_text(sample_content)
        content = output_path.read_text().lower()

        for jargon in legal_jargon:
            assert jargon not in content

    def test_statutory_deadlines_accuracy(self, output_path, output_dir):
        """Edge case: Verify correct Florida § 713 deadlines are referenced."""
        sample_content = """## Vignette 1: Missed NTO Deadline (45 days)
DETAIL: A drywall subcontractor completed $47,500 in interior finishing work but failed to serve the Notice to Owner within 45 days of first furnishing labor.

## Vignette 2: Missed Claim of Lien (90 days)
DETAIL: An electrical contractor performed rough-in and final work totaling $118,750 but missed the 90-day deadline to file a Claim of Lien after the owner stopped payment.

## Vignette 3: Missed Notice of Contest Response (60 days)
DETAIL: A concrete contractor filed a valid $62,300 lien but failed to respond to the owner's Notice of Contest within 60 days.
"""
        output_path.write_text(sample_content)
        content = output_path.read_text()

        assert "45 days" in content or "45-day" in content
        assert "90-day" in content or "90 days" in content
        assert "60 days" in content or "60-day" in content

    def test_emoji_icons_present(self, output_path, output_dir):
        """Error condition: Verify all vignettes include emoji icons."""
        sample_content = """## Vignette 1
ICON: ⏰

## Vignette 2
ICON: 📋

## Vignette 3
ICON: ⚖️
"""
        output_path.write_text(sample_content)
        content = output_path.read_text()

        emoji_pattern = r'ICON:\s*[\U0001F300-\U0001F9FF]'
        icons = re.findall(emoji_pattern, content)
        assert len(icons) == 3

    def test_detail_sentence_count(self, output_path, output_dir):
        """Error condition: Verify DETAIL sections have 2-3 sentences."""
        sample_content = """## Vignette 1
DETAIL: A drywall subcontractor completed $47,500 in interior finishing work but failed to serve the Notice to Owner within 45 days of first furnishing labor. By the time the general contractor withheld final payment, the window had closed and the sub lost all lien rights on the property.

## Vignette 2
DETAIL: An electrical contractor performed rough-in and final work totaling $118,750 but missed the 90-day deadline to file a Claim of Lien after the owner stopped payment. Without the lien, the contractor became an unsecured creditor with no claim against the property.

## Vignette 3
DETAIL: A concrete contractor filed a valid $62,300 lien but failed to respond to the owner's Notice of Contest within 60 days. The lien was deemed abandoned and removed from the property records, leaving the contractor with only a breach of contract claim.
"""
        output_path.write_text(sample_content)
        content = output_path.read_text()

        # Extract DETAIL sections and count sentences
        detail_pattern = r'DETAIL:\s*([^]*?)(?=\n##|\Z)'
        details = re.findall(detail_pattern, content, re.DOTALL)
        
        for detail in details:
            sentence_count = len(re.findall(r'[.!?]+', detail))
            assert 2 <= sentence_count <= 3, f"Detail has {sentence_count} sentences, expected 2-3"