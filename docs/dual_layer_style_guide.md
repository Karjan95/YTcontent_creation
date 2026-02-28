# Dual-Layer Style System — User Guide

**Date:** February 27, 2026

---

## What Is It?

The dual-layer style system lets you define **separate visual styles for characters and environments** in your production prompts. This is designed for hybrid styles — for example, stick figure characters placed in cinematic, richly detailed backgrounds.

Previously, the system treated visual style as one thing. If you set a minimalist style, everything became minimalist (including backgrounds). If you checked cinematic fields like aperture and depth of field, the system sometimes made your characters cinematic too. The dual-layer system eliminates this inconsistency.

---

## How to Use It

### Step 1: Upload Style References

Upload your reference images as usual. The style analysis will now automatically detect whether your references suggest a **hybrid** style (different treatment for characters vs environments) or a **unified** style (same treatment for everything).

### Step 2: Review the Style Panel

After style analysis completes, the Style Review panel now shows **two sub-panels**:

| Panel | Color | What It Controls |
|---|---|---|
| **Character Rendering** | Blue | How characters/subjects are drawn — description, detail level, writing style |
| **Environment Rendering** | Green | How backgrounds/scenes are rendered — description, scene complexity, camera language, lighting, framing, color palette, texture, mood |

At the top of the panel you'll see a **Rendering Mode** dropdown:

- **Unified** — One style applies to everything (traditional behavior)
- **Hybrid** — Characters and environments are rendered differently

### Step 3: Set the Rendering Mode

- If your style is consistent across characters and environments (e.g., full anime, full photorealism), leave it on **Unified**.
- If you want different treatments (e.g., stick figures in cinematic worlds, cartoon characters in painted landscapes), switch to **Hybrid**.

When you select **Hybrid**, the Environment Rendering panel highlights in yellow to remind you that environment fields will only apply to backgrounds, not to your characters.

### Step 4: Fill In Both Descriptions

- **Character Description** — Describe how ALL characters should look. Example: *"Simple stick figure with round head, dot eyes, thin line limbs. Flat black on white. No shading, no realistic features."*
- **Environment Description** — Describe how ALL backgrounds should look. Example: *"Rich cinematic environments with dramatic lighting, atmospheric depth, detailed textures, and volumetric effects."*

The more specific you are, the more consistent your results will be.

### Step 5: Check the Prompt Schema

Each checkbox in the prompt schema now has a small colored badge:

| Badge | Meaning |
|---|---|
| **CHR** (blue) | Field applies to characters only |
| **ENV** (green) | Field applies to environments only |
| **ALL** (purple) | Field applies to everything |

If you're in Hybrid mode with a minimalist detail level but have cinematic environment fields checked (like aperture, DOF, lighting), a **yellow warning banner** will appear:

> *"Hybrid style detected: cinematic fields will apply to environments only"*

This is informational, not an error. It confirms the system will route those fields to backgrounds only.

### Step 6: Approve and Generate

Click **Approve Style** as usual. The approved style now carries both character and environment rendering instructions into the production prompt pipeline.

In the generated prompts, you should see:
- Character/subject descriptions matching your character style (e.g., stick figures stay as stick figures)
- Environment/background descriptions matching your environment style (e.g., cinematic detail, camera effects)
- Technical camera fields (aperture, DOF, film stock) applied to the environment, not the character

---

## Tips for Best Results

1. **Be explicit in descriptions.** Vague descriptions like "simple style" give the model room to drift. Specific descriptions like "black line stick figure, no facial features, circle head, straight line body" lock it in.

2. **Use Hybrid mode for mixed styles only.** If your characters and environments share the same style, Unified mode produces better results because it doesn't split the instructions.

3. **Check the layer badges.** If a field is tagged ENV but you want it to affect characters too, Unified mode is the right choice.

4. **Reference images matter.** Upload images that clearly show both your character style AND your environment style. The style analysis uses these to auto-detect whether Hybrid mode is appropriate.

5. **Regeneration consistency.** The dual-layer system includes per-shot compliance checks in the prompt. This significantly reduces the random drift between runs where one generation is correct and the next ignores the style entirely.

---

## FAQ

**Q: What happens if I don't set a rendering mode?**
A: It defaults to Unified, which behaves exactly like the old system. Nothing breaks.

**Q: Can I switch between Unified and Hybrid after style analysis?**
A: Yes. The Rendering Mode dropdown is editable at any time before you approve the style.

**Q: Will my old saved projects still work?**
A: Yes. Old projects without the new fields will default to Unified mode with an empty environment description. Everything works as before.

**Q: I set Hybrid mode but my characters are still coming out cinematic. What's wrong?**
A: Check your Character Description field — make sure it explicitly describes the simplified style you want. Also ensure Detail Level is set to match (e.g., "Minimalist" or "Simplified" for stick figures).
