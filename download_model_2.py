from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen2.5-1.5B-Instruct"
target_dir = r"C:/Users/VigneshPandurangGaun/OneDrive - McLaren Strategic Solutions US Inc/Documents/models/llm/Qwen2.5-1.5B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype="auto")

tokenizer.save_pretrained(target_dir)
model.save_pretrained(target_dir)
