from rest_framework.renderers import JSONRenderer

class StandardizedJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = renderer_context['response'].status_code if renderer_context else 200
        
        # Determine status
        status_value = True if status_code < 400 else False
        
        # Avoid wrapping Swagger schema
        if renderer_context and renderer_context['request'].path.endswith('.yaml'):
            return super().render(data, accepted_media_type, renderer_context)
            
        # Avoid double-wrapping if the view already returned the correct format manually
        if isinstance(data, dict):
            keys = set(data.keys())
            # If it already explicitly looks like our standard format
            if 'status' in keys and ('data' in keys or 'message' in keys):
                # Optionally ensure all 3 keys exist
                if 'data' not in data:
                    data['data'] = None
                if 'message' not in data:
                    data['message'] = ""
                return super().render(data, accepted_media_type, renderer_context)
                
        # Extract message and data
        message = "Success" if status_value else "Error"
        payload = data
        
        if isinstance(data, dict):
            if 'detail' in data:
                message = data.pop('detail')
                payload = data if data else None
            elif 'message' in data:
                message = data.pop('message')
                payload = data if data else None
                
            # For DRF validation errors, it's often a dict of field errors
            if not status_value and payload:
                # If there's no explicit detail/message, it might be field errors
                if not message or message == "Error":
                    message = "Validation Error"

        response_data = {
            'status': status_value,
            'message': str(message),
            'data': payload
        }

        return super().render(response_data, accepted_media_type, renderer_context)
