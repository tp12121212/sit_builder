#!/usr/bin/env python3
import argparse
import sys
import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import re

# Initialize model
model = SentenceTransformer('all-MiniLM-L6-v2')

def extract_valid_bigrams(text, preserve_case=False):
    """Extract bigrams with strict single-space adjacency, line by line"""
    lines = re.split(r'[\r\n]+', text)
    all_bigrams = []
    
    for line in lines:
        pattern = r'\b([a-zA-Z]{3,}) ([a-zA-Z]{3,})\b'
        matches = re.findall(pattern, line)
        if preserve_case:
            bigrams = [f"{word1} {word2}" for word1, word2 in matches]
        else:
            bigrams = [f"{word1.lower()} {word2.lower()}" for word1, word2 in matches]
        all_bigrams.extend(bigrams)
    
    return all_bigrams

def analyze_stream(stream_name, stream_text, top_n=20, preserve_case=False):
    """Analyze a single stream and return top bigrams"""
    if not stream_text or len(stream_text.strip()) == 0:
        return {
            'stream_name': stream_name,
            'status': 'empty',
            'bigrams': []
        }
    
    # Extract bigrams
    valid_bigrams = extract_valid_bigrams(stream_text, preserve_case=preserve_case)
    unique_bigrams = list(set(valid_bigrams))
    
    if not unique_bigrams:
        return {
            'stream_name': stream_name,
            'status': 'no_bigrams',
            'bigrams': []
        }
    
    # Score bigrams
    doc_embedding = model.encode([stream_text])
    candidate_embeddings = model.encode(unique_bigrams)
    similarities = cosine_similarity(doc_embedding, candidate_embeddings)[0]
    
    # Create scored list
    scored_bigrams = list(zip(unique_bigrams, similarities))
    scored_bigrams.sort(key=lambda x: x[1], reverse=True)
    
    return {
        'stream_name': stream_name,
        'status': 'success',
        'total_bigrams': len(valid_bigrams),
        'unique_bigrams': len(unique_bigrams),
        'top_bigrams': [
            {'phrase': phrase, 'score': float(score)} 
            for phrase, score in scored_bigrams[:top_n]
        ]
    }

def main():
    parser = argparse.ArgumentParser(description="Extract and rank candidate bigrams")
    parser.add_argument("--preserve-case", action="store_true", dest="preserve_case")
    args = parser.parse_args()

    # Read JSON from stdin (piped from PowerShell)
    input_data = sys.stdin.read()
    
    try:
        # Parse JSON array of streams
        streams = json.loads(input_data)
        
        # Handle single object vs array
        if isinstance(streams, dict):
            streams = [streams]
        
        results = []
        
        # Process each stream
        for stream in streams:
            stream_name = stream.get('StreamName', 'Unknown')
            stream_text = stream.get('ExtractedStreamText', '')
            
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Processing: {stream_name}", file=sys.stderr)
            print(f"Text Length: {len(stream_text)} characters", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            
            analysis = analyze_stream(stream_name, stream_text, preserve_case=args.preserve_case)
            results.append(analysis)
        
        # Output final JSON
        print(json.dumps(results, indent=2))
        
    except json.JSONDecodeError as e:
        print(json.dumps({
            'error': 'Invalid JSON input',
            'details': str(e)
        }), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            'error': 'Processing error',
            'details': str(e)
        }), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
