"""A real CUDA kernel check, with CPU fallback on machines without a usable GPU."""
def inference_device():
    import torch
    try:
        if torch.cuda.is_available():
            # Availability alone does not prove the wheel supports the installed architecture.
            probe = torch.ones((8, 8), device='cuda')
            (probe @ probe).sum().item()
            torch.cuda.synchronize()
            return 'cuda:0'
    except (RuntimeError, AssertionError):
        pass
    return 'cpu'
