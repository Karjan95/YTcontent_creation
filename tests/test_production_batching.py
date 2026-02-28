import json
from unittest.mock import patch, MagicMock
from execution.research_scriptwriter import generate_production_table

def test_sequential_shot_numbering():
    """
    Test that generate_production_table produces sequential shot numbers
    even when processing multiple acts in parallel.
    
    Test case: 5 acts, ~1800 words total.
    """
    # Create 5 acts with multiple beats each
    narration_beats = []
    for act_idx in range(1, 6):
        for beat_idx in range(1, 11): # 10 beats per act = 50 beats total
            narration_beats.append({
                "act": f"ACT {act_idx}",
                "beat": f"Beat {beat_idx}",
                "text": "This is a sentence with about ten words to make it long. " * 4 # ~40 words per beat
            })
            
    # Total words = 50 * 40 = 2000 words (approx 1800-2000)
    narration_data = {
        "title": "Long Test Video",
        "narration": narration_beats
    }
    
    # Mock generate_content to return a few shots per batch
    # Since we have 50 beats and BEATS_PER_BATCH is 8, we expect ~7 batches.
    def mock_gen_content(prompt, **kwargs):
        # Extract shot_start_number from prompt to simulate Gemini obeying it
        import re
        match = re.search(r'"shot_number": "(\d+)"', prompt)
        start_num = int(match.group(1)) if match else 1
        
        # Return 2 shots per batch
        shots = [
            {
                "shot_number": str(start_num),
                "script_beat": "Sample text",
                "first_frame_prompt": "Prompt A",
                "last_frame_prompt": "Prompt A",
                "veo_prompt": "Veo A"
            },
            {
                "shot_number": str(start_num + 1),
                "script_beat": "Sample text 2",
                "first_frame_prompt": "Prompt B",
                "last_frame_prompt": "Prompt B",
                "veo_prompt": "Veo B"
            }
        ]
        
        # Continuity note
        continuity = [
            {
                "from_shot": str(start_num),
                "to_shot": str(start_num + 1)
            }
        ]
        
        return json.dumps({
            "shots": shots,
            "continuity_notes": continuity,
            "style_summary": "Test Style"
        })

    with patch('execution.research_scriptwriter.generate_content', side_effect=mock_gen_content):
        result = generate_production_table(narration_data, duration_minutes=15)
        
    assert "error" not in result
    assert result["success"] is True
    pt = result["production_table"]
    
    shots = pt["shots"]
    # 7 batches * 2 shots = 14 shots expected
    assert len(shots) > 10
    
    # Verify sequential numbering
    for i, shot in enumerate(shots):
        expected_num = str(i + 1)
        assert shot["shot_number"] == expected_num, f"Shot at index {i} has wrong number {shot['shot_number']}"
        
    # Verify continuity normalization
    continuity = pt["continuity_notes"]
    assert len(continuity) > 0
    for note in continuity:
        from_num = int(note["from_shot"])
        to_num = int(note["to_shot"])
        assert to_num == from_num + 1, f"Continuity break: {from_num} to {to_num}"
        
    print(f"Test passed: {len(shots)} shots correctly numbered sequentially.")

def test_frenetic_pacing():
    # 50 beats, Frenetic tier (3 beats per batch). Should create 17 batches.
    narration_beats = [{"act": f"ACT 1", "beat": f"Beat {i}", "text": "Short word."} for i in range(1, 15)]
    narration_data = {"title": "Fast Test", "narration": narration_beats}
    
    def mock_gen_content(prompt, **kwargs):
        import re
        match = re.search(r'"shot_number": "(\d+)"', prompt)
        start_num = int(match.group(1)) if match else 1
        return json.dumps({
            "shots": [{"shot_number": str(start_num), "script_beat": "x", "first_frame_prompt": "x", "last_frame_prompt": "y", "veo_prompt": "z"}],
            "continuity_notes": []
        })

    with patch('execution.research_scriptwriter.generate_content', side_effect=mock_gen_content):
        result = generate_production_table(narration_data, duration_minutes=15, pacing_tier="Frenetic")
    assert result["success"] is True
    pt = result["production_table"]
    # 14 beats / 3 beats per batch = 5 batches. Each mocked to return 1 shot.
    assert len(pt["shots"]) == 5

def test_meditative_pacing():
    # 16 beats, Meditative tier (12 beats per batch). Should create 2 batches.
    narration_beats = [{"act": f"ACT 1", "beat": f"Beat {i}", "text": "Short word."} for i in range(1, 17)]
    narration_data = {"title": "Slow Test", "narration": narration_beats}
    
    def mock_gen_content(prompt, **kwargs):
        import re
        match = re.search(r'"shot_number": "(\d+)"', prompt)
        start_num = int(match.group(1)) if match else 1
        return json.dumps({
            "shots": [{"shot_number": str(start_num), "script_beat": "x", "first_frame_prompt": "x", "last_frame_prompt": "y", "veo_prompt": "z"}],
            "continuity_notes": []
        })

    with patch('execution.research_scriptwriter.generate_content', side_effect=mock_gen_content):
        result = generate_production_table(narration_data, duration_minutes=15, pacing_tier="Meditative")
    assert result["success"] is True
    pt = result["production_table"]
    # 14 beats / 12 beats per batch = 2 batches (12 and 2). Each mocked to return 1 shot.
    assert len(pt["shots"]) == 2

if __name__ == "__main__":
    test_sequential_shot_numbering()
    test_frenetic_pacing()
    test_meditative_pacing()
