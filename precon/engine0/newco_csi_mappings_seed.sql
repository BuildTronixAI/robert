-- Engine 0 — CSI Division Entries + Initial Exact-Rule Mappings

INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('21', NULL, 'Fire Suppression', ARRAY['fire suppression','sprinkler','fire protection'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', NULL, 'Plumbing', ARRAY['plumbing','sanitary','domestic water','gas','medical gas'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-10', 'Plumbing Piping & Pumps', ARRAY['plumbing piping','domestic water piping','sanitary piping'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-11', 'Facility Water Distribution', ARRAY['domestic water','water distribution'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-13', 'Facility Sanitary Sewerage', ARRAY['sanitary','sewerage','waste','vent'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-30', 'Plumbing Equipment', ARRAY['water heater','booster pump','storage tank','plumbing equipment'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-40', 'Plumbing Fixtures', ARRAY['fixture','lavatory','toilet','urinal','sink'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-60', 'Gas Systems', ARRAY['gas','natural gas','gas piping'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('22', '22-63', 'Medical Gas', ARRAY['medical gas','lab gas','LVAC','CO2 piping'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', NULL, 'HVAC', ARRAY['HVAC','mechanical','heating','cooling','ventilation'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-07', 'HVAC Insulation', ARRAY['HVAC insulation','pipe insulation','duct insulation'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-09', 'Instrumentation & Control for HVAC', ARRAY['controls','DDC','BAS','BMS','temperature controls','commissioning'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-20', 'HVAC Piping & Pumps', ARRAY['hydronic piping','chilled water','hot water','pumps'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-21', 'Hydronic Piping', ARRAY['hydronic','chilled water piping','hot water piping'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-23', 'Refrigerant Piping', ARRAY['refrigerant','refrigerant piping'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-25', 'HVAC Water Treatment', ARRAY['water treatment','chemical feeder'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-31', 'HVAC Ducts & Casings', ARRAY['duct','ductwork','rectangular','spiral'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-33', 'Air Duct Accessories', ARRAY['damper','access door','fire damper','volume damper'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-36', 'Air Terminal Units', ARRAY['VAV','air terminal','ATB'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-37', 'Air Outlets & Inlets', ARRAY['diffuser','grille','air device'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-38', 'Ventilation Hoods', ARRAY['hood','kitchen hood','lab hood'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-50', 'Central Heating Equipment', ARRAY['boiler','central plant','heating equipment'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-64', 'Packaged Outdoor HVAC', ARRAY['RTU','packaged unit','rooftop'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-65', 'Cooling Towers', ARRAY['cooling tower'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-73', 'Air Handling Units', ARRAY['AHU','air handling unit','air handler'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-74', 'VRF Systems', ARRAY['VRF','variable refrigerant flow'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('23', '23-81', 'Unitary HVAC Equipment', ARRAY['PTAC','fan coil','FCU','unit heater'], 'GC', true) ON CONFLICT DO NOTHING;
INSERT INTO precon_e0_csi_entries (division_number, section_number, display_name, scope_keywords, mode_space, active) VALUES ('31', '31-23', 'Excavation & Fill', ARRAY['excavation','backfill','site excavation'], 'GC', true) ON CONFLICT DO NOTHING;

DO $$
DECLARE mv_id UUID;
BEGIN
  SELECT mapping_version_id INTO mv_id FROM precon_e0_mapping_versions WHERE version_string = 'MV-v1.0' LIMIT 1;
  IF mv_id IS NULL THEN RAISE EXCEPTION 'MV-v1.0 not found'; END IF;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-73', 'COST_CODE', '101', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "AHU \u2192 101 AIR HANDLING UNITS"}]'::JSONB, false, 'AHU → 101 AIR HANDLING UNITS', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-64', 'COST_CODE', '104', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "RTU \u2192 104 RTU/PACKAGED UNITS"}]'::JSONB, false, 'RTU → 104 RTU/PACKAGED UNITS', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-74', 'COST_CODE', '103', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "VRF \u2192 103"}]'::JSONB, false, 'VRF → 103', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-81', 'COST_CODE', '108', 'SUB', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Unitary HVAC \u2192 108 FAN-COIL"}]'::JSONB, false, 'Unitary HVAC → 108 FAN-COIL', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-81', 'COST_CODE', '107', 'SUB', 'MAPPED', 'EXACT_RULE', 0.9, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "PTAC under unitary HVAC"}]'::JSONB, false, 'PTAC under unitary HVAC', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-81', 'COST_CODE', '109', 'SUB', 'MAPPED', 'EXACT_RULE', 0.85, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Unit heaters"}]'::JSONB, false, 'Unit heaters', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-21', 'COST_CODE', '141', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Hydronic \u2192 141 AG CHW"}]'::JSONB, false, 'Hydronic → 141 AG CHW', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-21', 'COST_CODE', '142', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Hydronic \u2192 142 AG HW"}]'::JSONB, false, 'Hydronic → 142 AG HW', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-21', 'COST_CODE', '144', 'SUB', 'MAPPED', 'EXACT_RULE', 0.92, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Condenser water loop"}]'::JSONB, false, 'Condenser water loop', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-21', 'COST_CODE', '113', 'SUB', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Hydronic includes pumps"}]'::JSONB, false, 'Hydronic includes pumps', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-23', 'COST_CODE', '160', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Refrigerant \u2192 160"}]'::JSONB, false, 'Refrigerant → 160', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-09', 'COST_CODE', '172', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Controls \u2192 172 AMS CONTROLS"}]'::JSONB, false, 'Controls → 172 AMS CONTROLS', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-09', 'COST_CODE', '173', 'SUB', 'MAPPED', 'EXACT_RULE', 0.93, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Controls \u2192 173 COMMISSIONING"}]'::JSONB, false, 'Controls → 173 COMMISSIONING', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-09', 'COST_CODE', '502', 'BOTH', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Controls \u2192 502 TEMP CONTROLS (sub)"}]'::JSONB, false, 'Controls → 502 TEMP CONTROLS (sub)', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-31', 'COST_CODE', '221', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Rectangular duct \u2192 221"}]'::JSONB, false, 'Rectangular duct → 221', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-31', 'COST_CODE', '222', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Spiral duct \u2192 222"}]'::JSONB, false, 'Spiral duct → 222', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-33', 'COST_CODE', '231', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Volume dampers \u2192 231"}]'::JSONB, false, 'Volume dampers → 231', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-33', 'COST_CODE', '232', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Control dampers \u2192 232"}]'::JSONB, false, 'Control dampers → 232', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-33', 'COST_CODE', '233', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Fire dampers \u2192 233"}]'::JSONB, false, 'Fire dampers → 233', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-36', 'COST_CODE', '237', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Air terminal \u2192 237 VAV/ATB"}]'::JSONB, false, 'Air terminal → 237 VAV/ATB', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-37', 'COST_CODE', '261', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Air outlets \u2192 261 DIFFUSERS"}]'::JSONB, false, 'Air outlets → 261 DIFFUSERS', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-38', 'COST_CODE', '240', 'SUB', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Kitchen hoods \u2192 240"}]'::JSONB, false, 'Kitchen hoods → 240', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-38', 'COST_CODE', '239', 'SUB', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Lab hoods \u2192 239"}]'::JSONB, false, 'Lab hoods → 239', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-50', 'COST_CODE', '122', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Central heating \u2192 122 BOILERS"}]'::JSONB, false, 'Central heating → 122 BOILERS', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-65', 'COST_CODE', '123', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Cooling towers \u2192 123"}]'::JSONB, false, 'Cooling towers → 123', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-11', 'COST_CODE', '323', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Water dist \u2192 323 AG DOMESTIC WATER"}]'::JSONB, false, 'Water dist → 323 AG DOMESTIC WATER', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-13', 'COST_CODE', '321', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Sanitary \u2192 321 AG SAN WASTE"}]'::JSONB, false, 'Sanitary → 321 AG SAN WASTE', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-40', 'COST_CODE', '342', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Fixtures \u2192 342"}]'::JSONB, false, 'Fixtures → 342', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-30', 'COST_CODE', '343', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Plumbing eqp \u2192 343 WATER HEATER"}]'::JSONB, false, 'Plumbing eqp → 343 WATER HEATER', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-60', 'COST_CODE', '324', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Gas \u2192 324 AG GAS PIPING"}]'::JSONB, false, 'Gas → 324 AG GAS PIPING', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-63', 'COST_CODE', '331', 'SUB', 'MAPPED', 'EXACT_RULE', 0.97, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Med gas \u2192 331 MEDICAL GAS PIPING"}]'::JSONB, false, 'Med gas → 331 MEDICAL GAS PIPING', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '22-63', 'COST_CODE', '334', 'SUB', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Med gas testing \u2192 334"}]'::JSONB, false, 'Med gas testing → 334', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-07', 'COST_CODE', '501', 'BOTH', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "HVAC insulation \u2192 501"}]'::JSONB, false, 'HVAC insulation → 501', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '23-09', 'COST_CODE', '503', 'BOTH', 'MAPPED', 'EXACT_RULE', 0.93, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Controls/common work \u2192 503 TAB"}]'::JSONB, false, 'Controls/common work → 503 TAB', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '31-23', 'COST_CODE', '505', 'BOTH', 'MAPPED', 'EXACT_RULE', 0.95, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Excavation \u2192 505"}]'::JSONB, false, 'Excavation → 505', NOW()) ON CONFLICT DO NOTHING;

  INSERT INTO precon_e0_mappings (mapping_version_id, source_type, source_value, target_type, target_value, mode, mapping_status, rule_source, confidence, evidence, requires_review, reason, effective_from)
  VALUES (mv_id, 'CSI_SECTION', '31-23', 'COST_CODE', '139', 'SUB', 'MAPPED', 'EXACT_RULE', 0.92, '[{"type": "EXACT_RULE", "source": "workbook_extraction", "ref": "Project_Budget_Workbook_v2.2", "reasoning": "Site excavation \u2192 139 (mech scope)"}]'::JSONB, false, 'Site excavation → 139 (mech scope)', NOW()) ON CONFLICT DO NOTHING;

  UPDATE precon_e0_mapping_versions SET mapping_count = (SELECT COUNT(*) FROM precon_e0_mappings WHERE mapping_version_id = mv_id) WHERE mapping_version_id = mv_id;
END $$;