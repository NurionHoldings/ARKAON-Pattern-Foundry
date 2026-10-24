# Generation-time Visual DNA

Existing platform Intent_DNA remains immutable. The logo generator should produce a separate, versioned Visual DNA manifest alongside original artwork at generation time.

Each editable component has a stable layer ID, geometry, source reference (SVG node, text run or raster mask), stability classification, and links to the existing 12 Intent_DNA axes. The source and intent fingerprints bind the manifest to an immutable asset revision.

Edit routing: asset ID -> manifest version -> layer ID -> Intent impact -> authorization -> preview -> approval -> new immutable revision. CORE modifications require contract reopening and explicit approval.

Raster-only generation cannot guarantee semantic layers; mark segmentation as inferred rather than native. The current module is a draft contract and planning helper, not a production generator integration. PRODUCT_IMPLEMENT_HOLD remains in force.