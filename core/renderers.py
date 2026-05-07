from rest_framework.renderers import JSONRenderer

class StandardizedJSONRenderer(JSONRenderer):
    def _flatten_error(self, error_data):
        if error_data is None:
            return None
        if isinstance(error_data, list):
            if len(error_data) > 0:
                return self._flatten_error(error_data[0])
            return None
        if isinstance(error_data, dict):
            if error_data:
                first_key = next(iter(error_data))
                return self._flatten_error(error_data[first_key])
            return None
        return str(error_data)

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
            if 'status' in keys and ('data' in keys or 'message' in keys or 'error' in keys):
                is_success = data.get('status')
                
                if 'message' not in data:
                    data['message'] = ""
                    
                if is_success:
                    if 'data' not in data:
                        data['data'] = None
                    data.pop('error', None)
                else:
                    error_payload = data.pop('error', data.pop('data', None))
                    data['error'] = self._flatten_error(error_payload)
                    data.pop('data', None)
                    
                return super().render(data, accepted_media_type, renderer_context)
                
        # Extract message and data
        message = "Success" if status_value else "An error occurred"
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
                if not message or message == "An error occurred":
                    message = "Validation Error"

        response_data = {
            'status': status_value,
            'message': str(message),
        }
        
        if status_value:
            response_data['data'] = payload
        else:
            response_data['error'] = self._flatten_error(payload)

        return super().render(response_data, accepted_media_type, renderer_context)
